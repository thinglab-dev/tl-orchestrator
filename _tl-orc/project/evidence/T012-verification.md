# T012 — verificação

Registro sanitizado da verificação executada pelo Maker externo. Sem caminho, log,
configuração ou dado de consumidor. Todos os comandos rodaram offline, a partir da raiz do
pacote, na árvore de trabalho da branch `codex/token-efficiency-20260911` (baseline
`19f7a35bc750319fe072eab51cd2ac78c766bb0c`). Nenhum commit foi feito.

## Ambiente

- `python` 3.13.13, MSC v.1944 64 bit (AMD64)
- `Windows-11-10.0.26200-SP0`
- Sem rede; escritas de teste apenas em diretório temporário do sistema
  (`tempfile.TemporaryDirectory(prefix="tl-job-test-")`), removido ao fim de cada caso.

## Comandos e saídas

Esta seção registra os portões da **revisão final corrente** — a da rodada 15, com a guarda de
finalização comprovada — e mantém, em cada bloco marcado como tal, as execuções dirigidas das
rodadas anteriores que continuam válidas como histórico. A árvore de testes descrita aqui é a atual:
`tests/test_tl_job.py` com 91 casos em 20 classes. Contagens menores citadas em adendos antigos
valem para a árvore daquela rodada e não são prova desta.

### 1. Validador estrutural

```
python scripts/validate_repository.py
```

Saída literal:

```
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
```

Código de saída: `0`. Rodado na revisão final, depois das últimas edições em `CHANGELOG.md`
— relevante porque `validate_links` também varre `CHANGELOG.md` e `CONTRIBUTING.md`, e a
seção de migração passou a linkar `docs/EXECUTION_PROTOCOL.md#acoplar-ao-condutor-existente`.

O que este portão prova: manifesto canônico e coerente com a lista, a contagem literal e os
dois blocos de shell do `README.md`; JSON válido; frontmatter do `SKILL.md`; links locais e
âncoras resolvendo; nenhum arquivo distribuído linkando para caminho que só existe no
repositório; exportação e hashes coincidindo. O que ele não prova está na própria segunda
linha da saída: conferência estrutural não é prova de comportamento do método.

### 2. Casos dirigidos antes da suíte inteira

Os casos dirigidos da revisão final corrente são os de `ForgedTerminalResultTest`, com a vizinhança
de leitura do resultado terminal; eles estão com saída literal no adendo da rodada 15, ao fim deste
artefato, e rodaram antes da suíte completa, como em toda rodada.

Abaixo ficam as execuções dirigidas das rodadas anteriores, preservadas como histórico da mesma
árvore de testes. As contagens locais (`Ran 10`, `Ran 5`, `Ran 16`, `Ran 9`) são por classe
selecionada, não da suíte.

Os casos dirigidos da quarta rodada foram os que discriminam R1 — varredura que
falhou não vira contenção comprovada — e R2 — prazo em texto recusado dentro da fronteira
JSON —, mais os casos de grafia de caminho do achado transitório do host. Todos rodaram antes
da suíte completa daquela rodada.

```
python -m unittest tests.test_tl_job.SweepFailureTest tests.test_tl_job.SweepFailureReportTest tests.test_tl_job.PathSpellingTest -v
```

Saída literal:

```
test_a_reaped_leader_is_never_signalled_again (tests.test_tl_job.SweepFailureTest.test_a_reaped_leader_is_never_signalled_again) ... ok
test_graceful_sweep_stops_claiming_when_the_first_signal_fails (tests.test_tl_job.SweepFailureTest.test_graceful_sweep_stops_claiming_when_the_first_signal_fails) ... ok
test_graceful_sweep_that_works_reports_the_group_after_the_kill (tests.test_tl_job.SweepFailureTest.test_graceful_sweep_that_works_reports_the_group_after_the_kill) ... ok
test_job_object_that_refuses_to_terminate_is_not_reported_as_contained (tests.test_tl_job.SweepFailureTest.test_job_object_that_refuses_to_terminate_is_not_reported_as_contained) ... ok
test_job_object_that_terminates_is_the_only_case_reported_as_contained (tests.test_tl_job.SweepFailureTest.test_job_object_that_terminates_is_the_only_case_reported_as_contained) ... ok
test_process_group_that_is_provably_gone_still_counts_as_covered (tests.test_tl_job.SweepFailureTest.test_process_group_that_is_provably_gone_still_counts_as_covered)
A group that no longer exists is not a failed primitive: nothing survived it. ... ok
test_process_group_that_refuses_the_kill_is_not_reported_as_contained (tests.test_tl_job.SweepFailureTest.test_process_group_that_refuses_the_kill_is_not_reported_as_contained) ... ok
test_a_failed_sweep_recorded_on_disk_is_read_back_as_indeterminate (tests.test_tl_job.SweepFailureReportTest.test_a_failed_sweep_recorded_on_disk_is_read_back_as_indeterminate)
The refusal survives the file boundary: `result` re-reads and re-classifies it. ... ok
test_extended_spelling_does_not_let_a_path_out_of_the_state_directory (tests.test_tl_job.PathSpellingTest.test_extended_spelling_does_not_let_a_path_out_of_the_state_directory) ... ok
test_extended_spelling_of_the_same_directory_is_not_read_as_an_escape (tests.test_tl_job.PathSpellingTest.test_extended_spelling_of_the_same_directory_is_not_read_as_an_escape) ... ok

----------------------------------------------------------------------
Ran 10 tests in 1.821s

OK
```

Código de saída: `0`. Nenhum caso pulado aqui.

```
python -m unittest tests.test_tl_job.ContainmentTest tests.test_tl_job.IdentityTest -v
```

Saída literal:

```
test_descendant_stops_working_when_the_unit_times_out (tests.test_tl_job.ContainmentTest.test_descendant_stops_working_when_the_unit_times_out) ... ok
test_receipt_declares_the_containment_actually_used (tests.test_tl_job.ContainmentTest.test_receipt_declares_the_containment_actually_used) ... ok
test_concurrent_start_runs_the_unit_once (tests.test_tl_job.IdentityTest.test_concurrent_start_runs_the_unit_once) ... ok
test_divergent_manifest_is_refused_and_never_reuses_the_result (tests.test_tl_job.IdentityTest.test_divergent_manifest_is_refused_and_never_reuses_the_result) ... ok
test_same_identity_repeated_does_not_duplicate_the_unit (tests.test_tl_job.IdentityTest.test_same_identity_repeated_does_not_duplicate_the_unit) ... ok

----------------------------------------------------------------------
Ran 5 tests in 11.447s

OK
```

Código de saída: `0`. Estes cinco casos são a contraprova de que a correção de R1 não
enfraqueceu a contenção real (o neto continua parando no prazo) nem a idempotência sob
concorrência.

`InputTest` continua sendo a unidade dirigida das rodadas de entrada, agora com o caso novo de
R2 (`test_text_timeout_answers_in_json_without_claiming_or_waiting`). A saída literal da
rodada corrente está logo abaixo.

Os casos dirigidos da terceira rodada são os que discriminam o achado R1 daquela rodada —
contenção real da árvore `<state-dir>/jobs/<unidade>` em todos os comandos —, que ficam em
`InputTest` junto dos casos de link de `--result-file` e de prazo inválido das rodadas
anteriores. Por isso a classe inteira é a unidade dirigida, rodada antes da suíte.

```
python -m unittest tests.test_tl_job.InputTest -v
```

Saída literal da revisão final, com uma única elisão marcada: o caminho temporário absoluto
dentro da mensagem de skip foi substituído por `<tmp>`, porque este artefato é sanitizado e o
caminho é da máquina do Maker, não do método.

```
test_a_link_that_stays_inside_the_tree_is_still_accepted (tests.test_tl_job.InputTest.test_a_link_that_stays_inside_the_tree_is_still_accepted) ... ok
test_a_linked_state_tree_that_stays_inside_still_runs_once (tests.test_tl_job.InputTest.test_a_linked_state_tree_that_stays_inside_still_runs_once)
The resolution refuses the escape without breaking a contained link or idempotency. ... ok
test_identity_does_not_change_when_the_tree_starts_to_exist (tests.test_tl_job.InputTest.test_identity_does_not_change_when_the_tree_starts_to_exist) ... ok
test_invalid_timeout_is_refused_by_start_before_any_claim (tests.test_tl_job.InputTest.test_invalid_timeout_is_refused_by_start_before_any_claim) ... ok
test_invalid_timeout_is_refused_by_wait_before_the_loop (tests.test_tl_job.InputTest.test_invalid_timeout_is_refused_by_wait_before_the_loop)
An unusable bound must be refused at once, never waited on until it expires. ... ok
test_jobs_component_linked_out_of_the_state_directory_is_refused (tests.test_tl_job.InputTest.test_jobs_component_linked_out_of_the_state_directory_is_refused)
A valid state directory whose `jobs` is a link elsewhere writes nothing outside. ... ok
test_missing_command_is_refused_instead_of_invented (tests.test_tl_job.InputTest.test_missing_command_is_refused_instead_of_invented) ... ok
test_missing_working_directory_is_refused (tests.test_tl_job.InputTest.test_missing_working_directory_is_refused) ... ok
test_result_file_must_stay_inside_the_working_directory (tests.test_tl_job.InputTest.test_result_file_must_stay_inside_the_working_directory) ... ok
test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused (tests.test_tl_job.InputTest.test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused) ... skipped "this Windows session cannot create the link: [WinError 1314] O cliente não tem o privilégio necessário: '<tmp>\\outside-file\\leak.json' -> '<tmp>\\work\\escape-file.json'"
test_result_file_through_a_linked_directory_out_of_the_tree_is_refused (tests.test_tl_job.InputTest.test_result_file_through_a_linked_directory_out_of_the_tree_is_refused)
A contained spelling is not containment: the link is resolved before accepting. ... ok
test_state_directory_inside_the_package_is_refused (tests.test_tl_job.InputTest.test_state_directory_inside_the_package_is_refused) ... ok
test_text_timeout_answers_in_json_without_claiming_or_waiting (tests.test_tl_job.InputTest.test_text_timeout_answers_in_json_without_claiming_or_waiting)
A value like `nope` must reach the JSON refusal, not the parser's own exit. ... ok
test_unit_directory_linked_out_of_the_state_directory_is_refused (tests.test_tl_job.InputTest.test_unit_directory_linked_out_of_the_state_directory_is_refused) ... ok
test_unit_identifier_cannot_escape_the_state_directory (tests.test_tl_job.InputTest.test_unit_identifier_cannot_escape_the_state_directory) ... ok
test_unknown_unit_is_refused_by_status_and_wait (tests.test_tl_job.InputTest.test_unknown_unit_is_refused_by_status_and_wait) ... ok

----------------------------------------------------------------------
Ran 16 tests in 192.496s

OK (skipped=1)
```

Código de saída: `0`. O caso novo da quarta rodada é
`test_text_timeout_answers_in_json_without_claiming_or_waiting` (R2). Os três casos novos da
terceira rodada são
`test_jobs_component_linked_out_of_the_state_directory_is_refused`,
`test_unit_directory_linked_out_of_the_state_directory_is_refused` e
`test_a_linked_state_tree_that_stays_inside_still_runs_once`.

A execução dirigida abaixo é da rodada anterior e está mantida porque nada do que ela cobre
foi tocado nesta rodada; na revisão final esses nove casos passaram dentro da suíte completa.

```
python -m unittest tests.test_tl_job.ReceiptLimitsTest tests.test_tl_job.IdentityTest -v
```

Saída literal:

```
test_byte_ceiling_drops_optional_fields_and_keeps_the_core (tests.test_tl_job.ReceiptLimitsTest.test_byte_ceiling_drops_optional_fields_and_keeps_the_core) ... ok
test_clip_cuts_by_bytes_without_breaking_a_codepoint (tests.test_tl_job.ReceiptLimitsTest.test_clip_cuts_by_bytes_without_breaking_a_codepoint) ... ok
test_initial_receipt_carries_only_identity_and_locators (tests.test_tl_job.ReceiptLimitsTest.test_initial_receipt_carries_only_identity_and_locators) ... ok
test_large_stdout_stays_on_disk_and_out_of_the_receipt (tests.test_tl_job.ReceiptLimitsTest.test_large_stdout_stays_on_disk_and_out_of_the_receipt) ... ok
test_status_receipt_stays_at_identity_state_and_locators (tests.test_tl_job.ReceiptLimitsTest.test_status_receipt_stays_at_identity_state_and_locators) ... ok
test_unicode_survives_normalization_without_control_characters (tests.test_tl_job.ReceiptLimitsTest.test_unicode_survives_normalization_without_control_characters) ... ok
test_concurrent_start_runs_the_unit_once (tests.test_tl_job.IdentityTest.test_concurrent_start_runs_the_unit_once) ... ok
test_divergent_manifest_is_refused_and_never_reuses_the_result (tests.test_tl_job.IdentityTest.test_divergent_manifest_is_refused_and_never_reuses_the_result) ... ok
test_same_identity_repeated_does_not_duplicate_the_unit (tests.test_tl_job.IdentityTest.test_same_identity_repeated_does_not_duplicate_the_unit) ... ok

----------------------------------------------------------------------
Ran 9 tests in 7.739s

OK
```

Código de saída: `0`. Nenhum caso pulado aqui.

### 3. Suíte comportamental completa

```
python -m unittest discover -s tests -p "test_*.py"
```

Saída literal:

```
.....................................s...................................................s.
----------------------------------------------------------------------
Ran 91 tests in 338.918s

OK (skipped=2)
```

Código de saída: `0`. Uma passagem completa na revisão final da rodada 15, depois dos casos
dirigidos. São 91 casos em 20 classes — a árvore atual de testes, não as 52 da primeira entrega nem
as 78 da rodada 13. Os dois `s` são justificados e não escondem caso algum: um é o symlink de
arquivo que esta sessão de Windows não tem privilégio para criar, explicado em `### R1 — o escape
por link já existente é recusado` da segunda rodada; o outro é
`test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered`, cuja varredura por
grupo de processos só existe em POSIX (`skipped 'the process group branch only exists on POSIX; the
Linux CI exercises this case'`, conferido isoladamente com `python -m unittest
tests.test_tl_job.UnprovenSweepTest -v`). A regra que ele cobre continua exercitada aqui por
`test_an_unproven_scope_without_a_failure_is_indeterminate_on_any_platform`, que passou.
`ForgedTerminalResultTest` não está entre os pulados: em Windows
a trava exclusiva existe, e as três provas de finalização rodaram de verdade.

### 4. Higiene do diff

```
git diff --check
```

Sem saída; código de saída `0`. Limite deste portão, declarado em vez de escondido:
`git diff --check` só enxerga arquivo já rastreado, e `scripts/tl_job.py`, `tests/`,
`docs/EXECUTION_PROTOCOL.md` e os dois artefatos em `_tl-orc/project/` ainda estão como
`??` em `git status --porcelain` — este papel não faz `git add`. Esses arquivos foram
conferidos por busca direta de espaço em branco ao fim de linha (`[ \t]+$`), com zero
ocorrências.

## Cobertura comportamental dos 91 casos

Os 91 casos da árvore atual exercitam comportamento, não presença de string. Nomes reais,
por classe, na ordem em que aparecem em `tests/test_tl_job.py` (20 classes):

`ReceiptLimitsTest` (6)

- `test_large_stdout_stays_on_disk_and_out_of_the_receipt`
- `test_initial_receipt_carries_only_identity_and_locators`
- `test_status_receipt_stays_at_identity_state_and_locators`
- `test_byte_ceiling_drops_optional_fields_and_keeps_the_core`
- `test_unicode_survives_normalization_without_control_characters`
- `test_clip_cuts_by_bytes_without_breaking_a_codepoint`

`IdentityTest` (3)

- `test_same_identity_repeated_does_not_duplicate_the_unit`
- `test_concurrent_start_runs_the_unit_once`
- `test_divergent_manifest_is_refused_and_never_reuses_the_result`

`FailureTest` (10)

- `test_nonexistent_command_fails_explicitly_with_no_effects`
- `test_nonzero_exit_is_reported_as_unit_failure`
- `test_timeout_marks_uncertain_effects`
- `test_empty_return_never_becomes_success`
- `test_truncated_or_malformed_result_is_indeterminate`
- `test_outcome_outside_the_allowlist_is_refused`
- `test_oversized_result_file_is_refused`
- `test_blocked_and_ready_for_delivery_stay_distinct`
- `test_wait_timeout_is_not_a_unit_result`
- `test_result_without_terminal_state_is_indeterminate`

`InheritedResultTest` (2)

- `test_a_success_left_at_the_result_file_is_never_inherited_by_a_new_unit`
- `test_a_result_file_that_the_unit_itself_creates_is_still_admitted`

`InputTest` (16)

- `test_unit_identifier_cannot_escape_the_state_directory`
- `test_result_file_must_stay_inside_the_working_directory`
- `test_result_file_through_a_linked_directory_out_of_the_tree_is_refused`
- `test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused`
- `test_a_link_that_stays_inside_the_tree_is_still_accepted`
- `test_jobs_component_linked_out_of_the_state_directory_is_refused`
- `test_unit_directory_linked_out_of_the_state_directory_is_refused`
- `test_a_linked_state_tree_that_stays_inside_still_runs_once`
- `test_state_directory_inside_the_package_is_refused`
- `test_missing_command_is_refused_instead_of_invented`
- `test_invalid_timeout_is_refused_by_start_before_any_claim`
- `test_invalid_timeout_is_refused_by_wait_before_the_loop`
- `test_text_timeout_answers_in_json_without_claiming_or_waiting`
- `test_missing_working_directory_is_refused`
- `test_identity_does_not_change_when_the_tree_starts_to_exist`
- `test_unknown_unit_is_refused_by_status_and_wait`

`StatePathTest` (4)

- `test_status_reports_without_reading_any_log`
- `test_status_file_keeps_a_snapshot_without_history`
- `test_terminal_result_appears_atomically`
- `test_detach_uses_the_branch_of_this_platform`

`ContainmentTest` (2)

- `test_descendant_stops_working_when_the_unit_times_out`
- `test_receipt_declares_the_containment_actually_used`

`PathSpellingTest` (2)

- `test_extended_spelling_of_the_same_directory_is_not_read_as_an_escape`
- `test_extended_spelling_does_not_let_a_path_out_of_the_state_directory`

`SweepFailureTest` (7)

- `test_job_object_that_refuses_to_terminate_is_not_reported_as_contained`
- `test_job_object_that_terminates_is_the_only_case_reported_as_contained`
- `test_process_group_that_refuses_the_kill_is_not_reported_as_contained`
- `test_process_group_that_is_provably_gone_still_counts_as_covered`
- `test_graceful_sweep_stops_claiming_when_the_first_signal_fails`
- `test_graceful_sweep_that_works_reports_the_group_after_the_kill`
- `test_a_reaped_leader_is_never_signalled_again`

`SweepFailureReportTest` (1)

- `test_a_failed_sweep_recorded_on_disk_is_read_back_as_indeterminate`

`UnprovenSweepTest` (2)

- `test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered`
- `test_an_unproven_scope_without_a_failure_is_indeterminate_on_any_platform`

`AdmissionEssayTest` (1)

- `test_admitted_bytes_are_a_small_fraction_of_the_raw_log`

`StateComponentTypeTest` (5)

- `test_state_directory_that_is_a_file_is_refused_by_every_command`
- `test_jobs_component_that_is_a_file_is_refused_by_every_command`
- `test_unit_directory_that_is_a_file_is_refused_by_every_command`
- `test_creation_denied_by_the_platform_answers_in_json_without_claiming`
- `test_claim_denied_by_the_platform_answers_in_json_without_a_job_directory`

`ReportAllowlistTest` (6)

- `test_untouched_terminal_result_is_still_reported_in_full`
- `test_narrative_injected_after_the_terminal_state_is_never_retransmitted`
- `test_extra_field_inside_the_containment_record_is_refused`
- `test_outcome_that_was_never_admitted_is_not_read_as_success`
- `test_result_written_under_another_identity_is_indeterminate`
- `test_a_field_of_the_wrong_type_is_indeterminate`

`SupervisorFailureTest` (3)

- `test_failure_after_the_spawn_still_ends_the_unit_with_an_uncertain_result`
- `test_wait_reads_a_supervisor_gone_without_a_result_as_indeterminate`
- `test_a_held_lease_is_never_read_as_a_supervisor_that_ended`

`SupervisorBoundaryTest` (8)

- `test_a_job_directory_reached_through_a_link_is_refused_before_any_execution`
- `test_an_arbitrary_directory_as_state_directory_executes_no_claim_found_in_it`
- `test_a_claim_that_names_a_result_file_outside_both_trees_is_refused`
- `test_a_claim_with_fields_a_real_claim_never_carries_is_refused`
- `test_a_claim_from_another_schema_is_refused`
- `test_a_claim_written_for_another_unit_is_refused`
- `test_the_command_line_no_longer_offers_a_job_directory_to_execute`
- `test_a_real_claim_in_its_own_job_directory_still_runs`

`FinishedUnitTest` (1)

- `test_a_second_supervision_of_a_finished_unit_changes_nothing_on_disk`

`ClaimValidationTest` (6)

- `test_every_reader_refuses_a_claim_missing_a_field`
- `test_every_reader_refuses_a_claim_whose_fields_have_the_wrong_type`
- `test_result_refuses_a_broken_claim_before_reading_the_terminal_file`
- `test_reentering_start_over_a_broken_claim_refuses_instead_of_reusing_it`
- `test_a_claim_for_another_unit_is_refused_by_every_reader`
- `test_concurrent_starts_on_the_same_unit_leave_one_claim_and_one_receipt`

`ReceiptCeilingTest` (3)

- `test_a_receipt_stays_within_the_ceiling_when_disk_fields_are_huge`
- `test_the_ceiling_holds_when_the_core_keys_alone_overflow`
- `test_an_arbitrary_state_written_on_disk_never_becomes_receipt_text`

`ForgedTerminalResultTest` (3)

- `test_neither_wait_nor_result_delivers_while_the_forging_unit_keeps_writing`
- `test_the_same_unit_is_delivered_once_it_has_really_ended`
- `test_a_record_shorter_than_this_supervisor_writes_is_not_a_delivery`

Dois casos são regressões de defeitos encontrados durante a implementação:
`test_identity_does_not_change_when_the_tree_starts_to_exist` fixa a identidade lexical
(`os.path.abspath`), porque `Path.resolve()` no Windows canoniza de forma diferente para
caminho existente e inexistente, o que fazia a mesma unidade cair em `conflict`; e
`test_unicode_survives_normalization_without_control_characters` acompanha a escrita do
recibo como bytes UTF-8 em `sys.stdout.buffer`, porque `print` sob cp1252 levantava
`UnicodeEncodeError`.

## Ensaio de admissão (não é medição de tokens)

`test_admitted_bytes_are_a_small_fraction_of_the_raw_log` faz a unidade escrever 60000 linhas
de log (mais de 1 MB em `stdout.log`) e um resultado terminal curto. Ele então soma os bytes
UTF-8 do recibo inicial e do resultado admitido e afirma três coisas: o admitido fica abaixo
de um centésimo do log bruto; o admitido cabe em dois tetos de bytes; e o chefe é consultado
exatamente duas vezes, uma no despacho e uma no resultado terminal, contra uma por rodada de
acompanhamento no fluxo conversacional.

Este número é ilustração de admissão de saída de ferramenta, **não** medição de tokens e
**não** promessa de custo. Custo real depende do harness, do modelo e do cache em uso.
Nenhuma economia percentual é afirmada em nenhum artefato desta entrega.

## Primeira rodada de correção: prova por achado

Achados da revisão anterior, numerados naquela rodada. A numeração recomeça na rodada
seguinte, mais abaixo: os `R1` das duas seções são achados diferentes.

### R1 (primeira rodada) — a contenção discrimina, e não é só documentação

A sonda comparou dois builds do mesmo supervisor no mesmo cenário: unidade que gera um neto,
prazo estourado, e um neto que continua escrevendo em arquivo próprio depois do prazo. A sonda
ficou em `.tl-work/` e não é publicada; o que ela prova está fixado no teste versionado.

| build | `containment.kind` | `swept` | saída do `wait` | neto escreveu depois do prazo | bytes do arquivo do neto |
| --- | --- | --- | --- | --- | --- |
| anterior (só `terminate()`/`kill()` no filho direto) | `legacy_direct_child` | `direct_child` | `4` | `true` | 49 → 69 |
| corrigido | `windows_job_object` | `job_object` | `4` | `false` | 39 → 39 |

O quadro reproduz o achado do Root (`start_exit 0`, `wait_exit 4`,
`descendant_wrote_after_timeout: true`) e mostra o mesmo cenário contido depois da correção.
`test_descendant_stops_working_when_the_unit_times_out` fixa exatamente essa discriminação:
ele falha na revisão anterior e passa nesta. O prazo continua devolvendo saída `4` nos dois
builds — o que muda é o neto parar, não o código de saída.

Só a árvore deste despacho é tocada. Em Windows, o filho nasce suspenso e é atribuído ao Job
Object antes de executar a primeira instrução, então não existe janela para criar descendente
fora do objeto. Em POSIX, o grupo recebe `SIGTERM`, carência e `SIGKILL` enquanto o filho
direto ainda não foi colhido — a observação usa `os.waitid(..., WEXITED | WNOWAIT | WNOHANG)`,
que reporta a saída sem liberar o PID, de modo que o `pgid` sinalizado ainda é o desta unidade
e nunca um PID reciclado. Nenhum processo é localizado por nome ou por varredura do sistema.

Quando a contenção não pode ser estabelecida, o supervisor não mente sobre o efeito: antes de a
unidade rodar, o spawn é bloqueado (`start_failed`, `effects: none`); depois de efeitos já
ocorridos, `classify` devolve `effects: uncertain` com saída `5`. `swept` pode valer `unproven`,
e é isso que o recibo diz, em vez de afirmar término da árvore.
`test_receipt_declares_the_containment_actually_used` garante que o campo `containment`
(`established`, `kind`, `swept`) chega ao recibo entregue ao chefe, e não fica só no disco.

Limite declarado, não escondido: um descendente que chama `setsid()` sai do grupo POSIX e
sobrevive; o Job Object do Windows o contém. Está escrito em
`docs/EXECUTION_PROTOCOL.md`, seção `Contenção da árvore do job`.

### R5 (primeira rodada) — o exemplo executável bate com o parser

O exemplo mínimo do protocolo foi executado como argv, sem shell, por um driver Python de
apoio em `.tl-work/` (não publicado), para conferir que o que a documentação manda escrever é
exatamente o que o parser admite. Resultado: `start` saiu `0`, `wait` saiu `0`, e o recibo
trouxe `"observable_usage": "unknown"`, `"outcome": "ready_for_delivery"`,
`"result_status": "admitted"`, `"containment": {"established": true, "kind":
"windows_job_object", "swept": "job_object"}` e nenhum `dropped_fields`.

Isso importa porque `admit_result` aceita `observable_usage` apenas como string não vazia: um
`0` numérico ou um campo ausente não são o mesmo que "desconhecido". O exemplo do protocolo
passou a usar `unknown`, que é a forma correta de dizer que a métrica não foi observada. O
supervisor não coleta tokens, custo nem uso do harness, e nada nesta entrega afirma economia
percentual.

### R2, R3, R4 (primeira rodada) — mudanças de contrato

Estas três correções são de texto normativo e foram verificadas por leitura da árvore final,
mais o validador estrutural (links e âncoras, inclusive a nova
`#contenção-da-árvore-do-job`). Não há prova comportamental a produzir aqui, e nenhuma é
alegada.

- R2: a leitura linha a linha do diff integral é do Checker em `prompts/orchestrator.md`,
  `prompts/orchestrator-playbook.md`, `prompts/maker.md`, `prompts/checker-report-only.md` e
  `docs/EXECUTION_PROTOCOL.md`. O condutor confere identidade e revisão, cobertura, portões,
  destino dos riscos e uma amostra crítica dirigida, e pode despachar um verificador
  independente; o parecer integral não volta ao contexto dele.
  `prompts/orchestrator-perfis.md` foi inspecionado e já atribuía o diff inteiro ao Checker —
  não foi alterado.
- R3: a unidade padrão de topo passou a ser a story inteira (`<story>-<rodada>`) com a cadeia
  autorizada dentro dela; recibos de papel são internos. Job por papel é opcional, e microjobs
  não autorizam turnos de acompanhamento. O limite real está declarado: sem condutor adaptado
  lendo cada `result_file` e sem callback comprovado, vale uma unidade por vez.
- R4: papel designado com spec ratificada não reabre onboarding, triagem, planejamento nem
  Classificador do fluxo pai (`prompts/maker.md` e etapa 4 do `SKILL.md`). O bypass é de
  ativação: portões, limites de escrita e revisão independente continuam valendo, e nenhuma
  regra aplicável foi removida.

## Segunda rodada de correção: prova por achado

Achados da rodada anterior, mantidos aqui como registro. Só estes três foram tocados no
código naquela rodada, mais os metadados de release; onboarding, triagem e planejamento não
foram reabertos, T001–T011 não foram alteradas e nenhum estado foi promovido.

### R1 — o escape por link já existente é recusado

`check_result_file` validava o caminho só lexicamente: `os.path.normpath` mais
`Path.relative_to(cwd)`. Uma grafia contida não é contenção — se um componente do caminho já
existe como link para fora da árvore, `work/escape-dir/out.json` passa na checagem léxica e
escreve fora. A correção resolve os dois lados com `os.path.realpath` antes de aceitar e
recusa com `invalid_input`; o caminho **devolvido** continua sendo o léxico, para a impressão
do manifesto não mudar por causa da resolução.

Três casos comportamentais fixam a discriminação, todos offline e em diretório temporário:

| caso | montagem | esperado |
| --- | --- | --- |
| `test_result_file_through_a_linked_directory_out_of_the_tree_is_refused` | `work/escape-dir` → diretório fora da árvore | saída `2`, `state: invalid_input`, nada criado fora, nenhum job reivindicado |
| `test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused` | `work/escape-file.json` → arquivo fora da árvore | idem |
| `test_a_link_that_stays_inside_the_tree_is_still_accepted` | `work/inside-dir` → `work/reports` | aceito, e o caminho devolvido é o léxico |

Os dois casos negativos afirmam explicitamente `list(outside.iterdir()) == []`: a recusa é
comprovada por ausência de arquivo externo, não só pelo código de saída.

O caso de diretório roda nesta máquina Windows sem privilégio de symlink porque o helper cai
para junção de diretório (`cmd /c mklink /J`), que não exige
`SeCreateSymbolicLinkPrivilege` e é resolvida por `os.path.realpath` do mesmo jeito. O caso
de symlink de **arquivo** não tem esse substituto e foi pulado, com o motivo literal
(`[WinError 1314]`) na própria saída do teste — é o único `s` da suíte. Em Linux o helper usa
`os.symlink` direto e não pula: `skipTest` só é alcançado quando `os.name == "nt"`, então o
CI `ubuntu-latest` executa os dois casos ou falha.

Limite declarado, não escondido: isto recusa o **escape preexistente verificável**. Não
elimina corrida de sistema de arquivos contra quem troque um componente do caminho depois da
checagem e antes da escrita, e não enxerga hard link, que não tem alvo a resolver. Nenhuma
promessa é feita sobre ator adversarial com escrita concorrente na árvore de trabalho. Está
escrito em `docs/EXECUTION_PROTOCOL.md` e no comentário do próprio `check_result_file`.

### R2 — `wait` valida o prazo antes do laço

`command_wait` entrava no laço de polling com o valor recebido; `start` já validava. Agora os
dois chamam o mesmo `check_timeout`, que exige número **finito, acima de zero e no máximo
`TIMEOUT_MAX`** (86400 s) e nunca clampa: valor inválido vira `invalid_input` com saída `2`.
`NaN` e infinito são testados explicitamente (`seconds != seconds` e comparação com
`float("inf")`/`float("-inf")`), porque nenhum dos dois é pego por `0 < x <= limite`.

`test_invalid_timeout_is_refused_by_wait_before_the_loop` percorre `0`, `-1`, `nan`, `inf`,
`-inf` e `TIMEOUT_MAX + 1` contra uma unidade já reivindicada e afirma, além do estado e do
código de saída, que cada chamada retorna em menos de 30 s — é isso que distingue "recusado
antes do laço" de "esperou o prazo expirar". `test_invalid_timeout_is_refused_by_start_before_any_claim`
faz a mesma varredura no `start` e afirma que nenhum diretório de job foi criado.

A ajuda do `argparse` de `start` e de `wait` passou a dizer a mesma regra, e a seção do `wait`
em `docs/EXECUTION_PROTOCOL.md` registra que a validação acontece antes da espera.

### R3 — recibo bem-sucedido reduzido a identidade, estado e localizadores

O recibo de sucesso de `start` e `status` carregava `effects`, `authorization_fingerprint` e
`manifest_fingerprint`. As impressões não dão ao condutor nada acionável — ele não as compara
a nada — e `effects` no despacho era sempre o mesmo valor. O `receipt()` agora devolve
`schema`, `job_id`, `unit`, `state` e `locators`, e nada mais.

O que **não** mudou, por ser motivo observável ou identidade em uso:

- as impressões continuam no manifesto privado em disco e continuam sendo o que recusa um
  `start` divergente com `conflict` — `IdentityTest` (3 casos) passa sem alteração;
- `error_payload` mantém `effects` mais `error` em erro e conflito;
- o resultado terminal mantém `effects` vindo de `classify`, que devolve `none`, `known` ou
  `uncertain` — nunca outros valores, conferido na função;
- `wait_timeout` mantém `effects: uncertain`, passado explicitamente;
- um `start` que reaproveita a reivindicação mantém `reused: true`.

`test_initial_receipt_carries_only_identity_and_locators` e
`test_status_receipt_stays_at_identity_state_and_locators` afirmam o conjunto exato de chaves,
e o primeiro ainda confere que a autorização não aparece no recibo e que
`authorization_fingerprint` está no `manifest.json`. `enforce_ceiling` foi conferido: o
fallback de teto usa `if key in trimmed` sobre `CORE_KEYS`, então tolera a ausência de
`effects` sem levantar.

Nenhuma permissão foi acrescentada e nenhum critério de aceite foi mudado por esta redução.

### Metadados de release v0.8.0

As notas que estavam em `## [Unreleased]` foram movidas para `## [0.8.0] - 2026-09-11`,
deixando `Unreleased` vazio, e as três correções acima foram acrescentadas ao `### Alterado`
dessa seção. Não há string de versão em `SKILL.md` nem em `distribution-manifest.json`
(`format_version: 1` é formato, não release), então a mudança é só de `CHANGELOG.md`. As
referências de link do rodapé param em 0.4.0 e não foram estendidas. **Nada foi publicado**:
sem tag, sem commit, sem push.

## Terceira rodada de correção: prova por achado

Dois achados. Só o primeiro toca código; o segundo é registro. Onboarding, triagem e
planejamento não foram reabertos, T001–T011 não foram alteradas, nenhum estado foi promovido e
nada fora dos pontos apontados foi mexido.

### R1 — a árvore da unidade é conferida por resolução de links, em todos os comandos

`job_directory` fazia só `os.path.normpath` mais a comparação léxica `job_dir.parent != jobs`.
Isso barra `..` na grafia, mas não barra um `--state-dir` válido cujo `jobs`, ou cuja unidade,
já exista como link apontando para fora: a grafia continua contida e o `mkdir`, a
reivindicação, o manifesto, o `status.json` e os logs caem fora da árvore de estado.

A correção resolve os dois componentes com `os.path.realpath` antes de qualquer efeito e
recusa com `invalid_input`, saída `2`. Duas funções compartilhadas passaram a existir,
`real()` e `contained()`, e `check_result_file` foi reescrito para usar a segunda — mesma
mensagem, mesmo comportamento, menos duplicação. O caminho **devolvido** por `job_directory`
continua sendo o léxico, porque `manifest_fingerprint` é calculado a partir dele e a
identidade não pode mudar por causa da resolução.

Cobre todos os comandos pertinentes porque todos passam por essa função antes do primeiro
efeito, conferido linha a linha: `command_start` (antes de `job_dir.parent.mkdir` e de
`job_dir.mkdir()`), `command_status` (antes de `job_dir.is_dir()` e da leitura), `command_wait`
(antes do laço) e `command_result` (antes de `read_json`). O `supervise` interno foi deixado
como estava de propósito: ele recebe um diretório já validado pelo `start` e não tem raiz de
estado com que comparar.

Três casos comportamentais, offline e em diretório temporário:

| caso | montagem | esperado |
| --- | --- | --- |
| `test_jobs_component_linked_out_of_the_state_directory_is_refused` | `<state>/jobs` → diretório fora | `start`, `status`, `wait` e `result` devolvem `2` com `state: invalid_input`, nada criado fora |
| `test_unit_directory_linked_out_of_the_state_directory_is_refused` | `<state>/jobs/T012` → diretório fora | idem |
| `test_a_linked_state_tree_that_stays_inside_still_runs_once` | `<state>/jobs` → `<state>/real-jobs` | roda, e o segundo `start` devolve `reused: true` |

Os dois negativos varrem os quatro comandos, inclusive os de leitura, e afirmam três coisas em
cada um: código `2`, `state: invalid_input` e `sorted(p.name for p in outside.iterdir()) == []`
— a recusa é comprovada por ausência de arquivo externo, não só pelo código de saída. Afirmam
também que cada chamada volta em menos de 8 s, o que distingue "recusado antes do laço" de
"esperou o prazo". O terceiro caso existe para provar que a resolução não quebra link contido
nem idempotência.

Prova de discriminação, fora da árvore publicada: uma cópia de `scripts/` e `tests/` em
`.tl-work/jobs-link-probe/` com `job_directory` revertido ao léxico puro. Comando e saída
literais, com a lista de falhas recortada nas linhas de asserção:

```
python -m unittest tests.test_tl_job.InputTest.test_jobs_component_linked_out_of_the_state_directory_is_refused tests.test_tl_job.InputTest.test_unit_directory_linked_out_of_the_state_directory_is_refused tests.test_tl_job.InputTest.test_a_linked_state_tree_that_stays_inside_still_runs_once
```

```
AssertionError: 0 != 2 : start
AssertionError: 3 != 2 : start
----------------------------------------------------------------------
Ran 3 tests in 97.050s

FAILED (failures=2)
```

Lido literalmente: com o código antigo, o caso de `jobs` linkado devolvia `0` — aceitava e
escrevia através do link — e o caso da unidade linkada devolvia `3` (`conflict`), ou seja
lia e reivindicava através do link. O terceiro caso passou nas duas versões, então os casos
novos não falham por construção; eles falham exatamente pelo defeito. A sonda fica em
`.tl-work/`, não é publicada e não entra no manifesto.

Limite declarado, não escondido: isto recusa o **escape por link já existente no momento da
checagem**. Não promete imunidade a corrida adversarial de sistema de arquivos, em que um
componente é trocado depois da conferência e antes do uso, e não enxerga hard link, que não
tem alvo a resolver. Está escrito no comentário do próprio `job_directory`, no `CHANGELOG.md`
e na seção `Limites` de `docs/EXECUTION_PROTOCOL.md`.

### R2 — autoridade do fechamento de release, sem afirmar publicação

A spec congelada e o AC07 descreviam desenvolvimento, cujo lugar de nota é `## [Unreleased]`.
O adendo do usuário de 2026-09-11 ("vá dando pull-requests e merges ou releases quando
necessário", "Termine aí"), registrado na seção `Autoridade posterior de publicação` da spec,
autorizou expressamente fechar release — e o passo 3 do `CONTRIBUTING.md` exige mover as notas
para a versão datada **antes** da tag. Por isso `## [0.8.0] - 2026-09-11` fica datada e
`## [Unreleased]` fica vazia.

O AC07 e a linha de resultado de `T012-execucao-economica-por-artefatos.md` foram reescritos
para distinguir os dois regimes. Nenhum critério técnico mudou. E o registro é explícito no
que **não** aconteceu: não há commit, tag, push nem release feitos por este papel; o passo de
publicação é do condutor, depois dos portões e da revisão. `## Review` continua `Pendente` —
T012 segue aguardando revisão final independente até haver evidência.

## Quarta rodada de correção: prova por achado

Dois achados apontados (R1 alto, R2 médio) mais a nota do host sobre uma falha transitória em
Windows. Só `scripts/tl_job.py` e `tests/test_tl_job.py` foram tocados. Onboarding, triagem e
planejamento não foram reabertos, T001–T011 não foram alteradas, nenhum estado foi promovido,
nenhuma dependência ou serviço foi acrescentado e nada fora dos pontos apontados foi mexido.

### R1 — varredura que falhou não vira contenção comprovada

`JobObjectContainment.sweep` chamava `TerminateJobObject` e devolvia `job_object` sem olhar o
retorno; `PosixSessionContainment.sweep` chamava `os.killpg` e devolvia `process_group` mesmo
quando o `SIGKILL` não chegava. Nos dois casos o recibo afirmava escopo comprovado enquanto
parte da árvore podia continuar viva e escrevendo — e `classify` seguia para `known`, saída
`0`.

A correção separa escopo de falha. `sweep` passa a devolver `Sweep(scope, failure)`;
`signal_group` passa a ser de três valores — `sent`, `absent` quando o grupo comprovadamente
não existe mais (`ProcessLookupError`), ou o texto do motivo quando o sinal falhou de verdade
(por exemplo `PermissionError`). Falha real vira `Sweep("unproven", motivo)`, `describe`
acrescenta `sweep_failed` ao registro (recortado em 160 bytes) e `classify` ganhou um ramo
**antes** do ramo de prazo:

```python
if isinstance(containment, dict) and containment.get("sweep_failed"):
    # The ending primitive itself failed: part of the tree may still be running
    # and writing, so no outcome read from disk can be called final here.
    return "uncertain", EXIT_INDETERMINATE
```

Ou seja: primitiva de encerramento falhou ⇒ escopo `unproven`, resultado indeterminado,
`effects: uncertain`, saída `5`. Grupo comprovadamente ausente continua sendo cobertura, não
falha — ninguém sobreviveu à varredura.

Sete casos negativos e positivos discriminantes, em dublê controlado (`FakeJobApi` responde ao
`TerminateJobObject` como mandado; `os.killpg` é substituído por uma função que registra
`(pgid, número)` e levanta a exceção pedida). O ramo POSIX roda em qualquer plataforma porque
os números de sinal são apenas nomes no dublê:

| caso | primitiva forçada a | esperado |
| --- | --- | --- |
| `test_job_object_that_refuses_to_terminate_is_not_reported_as_contained` | `TerminateJobObject` devolve `0` | `scope == "unproven"`, `sweep_failed` cita `TerminateJobObject`, `classify → ("uncertain", 5)` |
| `test_job_object_that_terminates_is_the_only_case_reported_as_contained` | `TerminateJobObject` devolve `1` | `job_object`, sem `sweep_failed`, `classify → ("known", 0)` |
| `test_process_group_that_refuses_the_kill_is_not_reported_as_contained` | `killpg` levanta `PermissionError` | `unproven`, saída `5`, e só o `pgid` próprio foi sinalizado |
| `test_process_group_that_is_provably_gone_still_counts_as_covered` | `killpg` levanta `ProcessLookupError` | `process_group`, sem falha, `calls == [(424242, 9)]` |
| `test_graceful_sweep_stops_claiming_when_the_first_signal_fails` | `SIGTERM` falha | recusa imediata, `calls == [(424242, 15)]` — nem espera a carência |
| `test_graceful_sweep_that_works_reports_the_group_after_the_kill` | ambos funcionam | `calls == [(424242, 15), (424242, 9)]` |
| `test_a_reaped_leader_is_never_signalled_again` | líder já colhido | `unproven` com `failure is None`, nenhum sinal enviado |

`test_a_failed_sweep_recorded_on_disk_is_read_back_as_indeterminate` fecha o outro lado: um
`result.json` com `swept: "unproven"` e `sweep_failed` é relido por `result`, que devolve saída
`5` e `effects: uncertain` mantendo `outcome: delivered`. A recusa atravessa a fronteira de
arquivo, não vive só na memória do `wait`.

Duas propriedades foram preservadas de propósito e estão afirmadas nos próprios casos: só o
`pgid` desta unidade e só o handle deste job object são tocados — nenhuma varredura do sistema,
nenhum processo alheio —, e a morte real dos descendentes continua provada por
`ContainmentTest`, que roda processo de verdade e confere que o neto para de escrever após o
prazo.

Prova de discriminação por mutação, em cópia em diretório temporário (não publicada), com as
duas varreduras revertidas para ignorar o retorno da primitiva. Comando literal; a saída está
recortada nas linhas de asserção, cada uma anotada entre parênteses com o caso a que pertence,
e o rodapé é literal:

```
python -m unittest tests.test_tl_job.SweepFailureTest
```

```
AssertionError: 'process_group' != 'unproven'   (test_graceful_sweep_stops_claiming_when_the_first_signal_fails)
AssertionError: 'job_object' != 'unproven'      (test_job_object_that_refuses_to_terminate_is_not_reported_as_contained)
AssertionError: 'process_group' != 'unproven'   (test_process_group_that_refuses_the_kill_is_not_reported_as_contained)
----------------------------------------------------------------------
Ran 7 tests in 2.015s

FAILED (failures=3)
```

Os quatro casos que continuam passando no mutante são os positivos e o de grupo ausente: os
novos não falham por construção, falham exatamente pelo defeito.

### R2 — `--timeout` em texto chega à fronteira JSON

`--timeout` era declarado com `type=float` nos dois subcomandos. Com `--timeout nope`, o
`argparse` convertia antes de qualquer handler e saía com a **própria** mensagem de uso em
`stderr`, sem recibo JSON — o chefe recebia saída `2` sem `state`, sem `error` e sem contrato.

A correção tira `type=float` de `start` e de `wait` e valida o texto dentro da fronteira
`JobError`, em `check_timeout`, com comentário no lugar dizendo por que o valor é recebido
como texto. `float()` inválido vira `invalid_input` com saída `2`; `nan`, `inf`, `-inf`, `0`,
negativo e acima de `TIMEOUT_MAX` continuam recusados pelas mesmas comparações de antes —
nenhum limite já coberto foi afrouxado.

`test_text_timeout_answers_in_json_without_claiming_or_waiting` varre `nope`, `""`, `" "`,
`1,5`, `10s`, `0x10`, `None` e `1e` em `start` e em `wait`, e afirma, em cada um: saída `2`,
`state: invalid_input`, payload compacto na saída padrão e — no fim — `self.state.exists()`
falso. Nada foi reivindicado, nada foi escrito, nada foi esperado.

Prova de discriminação por mutação, em cópia temporária com `type=float` restaurado nos dois
subcomandos — saída recortada no bloco da asserção e no rodapé, sem as linhas em branco que a
captura do `stderr` inseriu:

```
python -m unittest tests.test_tl_job.InputTest.test_text_timeout_answers_in_json_without_claiming_or_waiting
```

```
AssertionError: '' is not true : no receipt on stdout; stderr=usage: tl_job.py start [-h] --state-dir STATE_DIR --unit UNIT
                       --authorization AUTHORIZATION --cwd CWD
                       --timeout TIMEOUT [--result-file RESULT_FILE]
tl_job.py start: error: argument --timeout: invalid float value: 'nope'

----------------------------------------------------------------------
Ran 1 test in 0.139s

FAILED (failures=1)
```

### Nota do host: a falha transitória em Windows tinha causa concreta

O host relatou uma falha transitória em `test_concurrent_start_runs_the_unit_once`, com
recusa de contenção. Ela foi reproduzida aqui antes de qualquer mudança: **1 falha em 12**
execuções isoladas do caso, com

```
{"state": "invalid_input", "error": "job directory resolves outside the state directory through a link", "effects": "none"}
```

Uma cópia instrumentada em diretório temporário, que imprime as duas resoluções, falhou na
**execução 2 de 40** e mostrou a causa:

```
real_child=C:\...\tl-job-test-<id>\state\jobs\T012
real_root=\\?\C:\...\tl-job-test-<id>\state\jobs
child_exists=False root_exists=False
```

O mesmo diretório em duas grafias. Quando um `start` concorrente cria `jobs` no meio da
verificação, o `os.path.realpath` do Windows pode devolver a grafia estendida `\\?\` da
mesma pasta — o CPython mantém o prefixo quando a reconferência da grafia simples falha com
outro `winerror`. Duas grafias de um diretório só liam como escape.

A correção está em `real()` e é **só de grafia**: em `os.name == "nt"`, o prefixo `\\?\` (e
`\\?\UNC\`, que volta a `\\`) é normalizado antes da comparação. A resolução de links em si
não foi tocada, `contained()` e `job_directory()` ficaram idênticos, e nenhuma recusa foi
enfraquecida.

Dois casos guardam os dois lados, marcados `skipUnless(os.name == "nt")` porque a grafia
estendida só existe em Windows: o positivo prova que a grafia estendida do mesmo diretório não
é escape, e o negativo prova que ela **não** deixa um caminho sair do diretório de estado
(`JobError` com saída `2`). Prova de discriminação por mutação, com `real()` revertido a
`Path(os.path.realpath(path))` — saída recortada, com o caminho temporário absoluto elidido
como `...` por ser da máquina do Maker:

```
python -m unittest tests.test_tl_job.PathSpellingTest -v
```

```
test_extended_spelling_does_not_let_a_path_out_of_the_state_directory ... ok
test_extended_spelling_of_the_same_directory_is_not_read_as_an_escape ... FAIL
AssertionError: WindowsPath('//?/C:/Users/.../state/jobs') != WindowsPath('C:/Users/.../state/jobs')
----------------------------------------------------------------------
Ran 2 tests in 0.006s

FAILED (failures=1)
```

O controle negativo continua recusando o escape real no mutante — a correção não é um
afrouxamento disfarçado. Depois da correção, o caso de concorrência rodou **40 vezes seguidas
sem falha** (antes: 1 falha em 12), e a suíte completa passou.

Hipóteses que foram levantadas e **rejeitadas** durante a investigação dirigida, registradas
como rejeitadas e não como achados: estresse de `realpath` em threads no mesmo processo sob
criação/remoção de diretórios (0 divergências); sonda entre processos com 400 rodadas × 4
processos (0 divergências); janela de renomeação de diretório (descartada por leitura de
`command_start` — diretórios de job nascem de `mkdir` simples e `write_atomic` só renomeia
arquivo dentro da mesma pasta); redirecionamento de sistema de arquivos de Python de loja
(`realpath` de caminho existente e inexistente idêntico). A investigação parou quando a cópia
instrumentada deu causa concreta, como pedido.

## Limites desta verificação

- Os portões acima são transporte e conferência estrutural. Saída zero não aprova a story,
  não substitui os portões do condutor e não substitui o Checker independente.
- A validação local cobriu o ramo Windows, incluindo o Job Object. O ramo POSIX da contenção
  — sessão própria, `SIGTERM`/carência/`SIGKILL` no grupo antes da colheita — é exercitado
  pelo CI Linux, que passou a rodar `python3 -m unittest discover -s tests -p "test_*.py" -v`
  depois do validador em `.github/workflows/validate.yml`, com comentário explicitando que o
  runner `ubuntu-latest` cobre o caso do neto em `ContainmentTest`. Esse resultado ainda não
  existe nesta árvore, porque o Maker externo não faz commit nem push: quem publicar deve
  conferir a execução do workflow antes de tratar o ramo POSIX como provado.
- Um caso da suíte não rodou aqui: `test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused`
  foi pulado porque esta sessão Windows não tem `SeCreateSymbolicLinkPrivilege`, e o motivo
  literal aparece na saída. O caso de diretório do mesmo achado rodou, por junção. Quem
  publicar deve conferir a execução do workflow Linux antes de tratar o symlink de arquivo
  como provado; lá o helper não tem caminho de skip.
- A recusa de escape por link vale para o link já existente no momento da checagem, tanto na
  árvore `<state-dir>/jobs/<unidade>` quanto em `--result-file`. Corrida de sistema de
  arquivos e hard link continuam fora do que é afirmado.
- Os casos de link da árvore de estado rodaram aqui por junção de diretório (`mklink /J`),
  não por symlink, porque esta sessão Windows não tem `SeCreateSymbolicLinkPrivilege`. Os dois
  resolvem por `os.path.realpath` do mesmo jeito, e em Linux o helper usa `os.symlink` direto;
  quem publicar deve conferir a execução do workflow antes de tratar o ramo symlink como
  provado.
- Os sete casos de `SweepFailureTest` provam a **decisão** da varredura com a primitiva forçada
  a falhar em dublê controlado, não a falha real do kernel: nenhuma sessão aqui consegue fazer
  `TerminateJobObject` ou `SIGKILL` falharem de verdade sob demanda. O que roda com processo de
  verdade é `ContainmentTest`, que continua provando que o descendente para. A combinação é o
  que é afirmado; falha real de primitiva em produção não foi observada.
- Os dois casos de `PathSpellingTest` só rodam em Windows (`skipUnless`), porque a grafia
  `\\?\` não existe em POSIX. Em Linux eles são pulados por desenho, e o normalizador é um
  ramo `os.name == "nt"` inerte lá.
- A falha transitória do host foi reproduzida e corrigida com causa concreta identificada. As
  40 execuções seguidas sem falha depois da correção são evidência forte, não prova de
  ausência: corrida de sistema de arquivos sob concorrência é probabilística por natureza.
- Nenhum estado foi promovido: `operational_verified` não foi tocado, o STATUS global não foi
  substituído e T001–T011 não foram alteradas.
- O método continua utilizável sem Python. O supervisor é opcional; os limites de automação
  estão declarados em `docs/EXECUTION_PROTOCOL.md`, seção `Limites`.

## Adendo — correção dos dois achados do Checker (2026-09-11)

Duas correções entraram depois do registro acima: componente do estado preexistente como
arquivo (recusa em JSON antes de qualquer escrita, com a família de `OSError` tratada nas
fronteiras de criação e reivindicação) e `report` reconstruindo a resposta por allowlist em vez
de copiar `result.json`.

Nesta rodada rodaram **apenas testes dirigidos**, em Windows, offline:

- `python -m unittest tests.test_tl_job.StateComponentTypeTest tests.test_tl_job.ReportAllowlistTest -v`
  → 11 testes, OK.
- `python -m unittest tests.test_tl_job.FailureTest tests.test_tl_job.SweepFailureReportTest`
  → 11 testes, OK.

A suíte completa é executada pelo **condutor host**, como portão sobre a árvore final de cada
rodada — não por este papel, e não sobre um estado intermediário. As saídas da árvore final desta
rodada são registradas pelo host na seção de fechamento desta evidência, depois da revisão
independente. Os números de suíte citados nas seções anteriores pertencem às árvores finais das
rodadas em que foram registrados.

## Adendo — falha interna do supervisor não deixa a unidade sem resposta (2026-09-11)

Achado corrigido nesta rodada, na fronteira estrita apontada: exceção ao abrir log ou ao gravar
`status.json`/`result.json` dentro de `supervise` podia encerrar o supervisor **sem** finalizar a
unidade — árvore não varrida, nenhum arquivo terminal — e o `wait` só devolvia `wait_timeout`
depois de gastar o prazo inteiro. Só `scripts/tl_job.py`, `tests/test_tl_job.py`,
`docs/EXECUTION_PROTOCOL.md` e `CHANGELOG.md` foram tocados. Nada foi redesenhado, nenhum
onboarding ou chat foi reaberto, T001–T011 e o STATUS global não foram alterados, nenhuma
dependência ou serviço foi acrescentado (biblioteca padrão), e nenhum commit, tag ou push foi
feito.

### O que a correção faz

- `supervise` foi dividido em `run_supervised` → `execute_unit` → `run_under_containment` +
  `finalize`, com um registro mutável `UnitRun`, para que **toda** saída ainda finalize a unidade.
- `run_under_containment` encerra a árvore em `finally` pela **mesma contenção** que a possui
  (varredura antes da colheita, depois `close()`), inclusive quando uma operação interna falhou:
  uma unidade nunca sobrevive ao supervisor que responde por ela.
- `internal_failure` classifica exceção interna como `crashed` com `effects: uncertain` sempre que
  a unidade **pode** ter rodado (`run.unit_ran` é marcado imediatamente após o `Popen`), e só usa
  `start_failed`/`none` quando está provado que nenhum filho existiu. Falha posterior **não** é
  rebaixada a `none`. `ContainmentError.unit_ran` foi conferido função a função: adoção POSIX
  falhando passa `True`; em Windows, atribuição ao job e resume falhando mantêm `False` porque o
  filho segue suspenso e nunca executou.
- Disco que impede gravar o `result.json` final devolve saída `5` sem repetir a escrita e sem
  inventar arquivo terminal. `write_atomic` remove seu próprio temporário quando a escrita falha,
  para nenhum leitor encontrar nome meio escrito.
- Liveness do supervisor passa a ser provada por **lease exclusivo do sistema operacional**
  (`supervisor.lock`, `fcntl.flock`/`msvcrt.locking`), liberado pelo SO na saída ou no crash —
  nunca por PID, que pode ser reciclado. `supervisor.json` guarda só identidade legível.
  Plataforma sem a primitiva responde `unknown`, e lease **ausente** também é `unknown`, nunca
  "morto".
- `command_wait` passa a ler esse lease dentro do laço: ninguém detendo o lease por uma janela
  curta (`LEASE_GRACE_SECONDS`, 5 s, que cobre a corrida do supervisor recém-nascido) e sem
  `result.json` responde `indeterminate`/`effects: uncertain`/saída `5`, em vez de espera até o
  prazo. Um segundo supervisor no mesmo job encontra `busy` e recusa com `conflict`.

### Casos dirigidos, rodados antes de qualquer suíte

```
python -m unittest tests.test_tl_job.SupervisorFailureTest -v
```

Saída literal:

```
test_a_held_lease_is_never_read_as_a_supervisor_that_ended (tests.test_tl_job.SupervisorFailureTest.test_a_held_lease_is_never_read_as_a_supervisor_that_ended) ... ok
test_failure_after_the_spawn_still_ends_the_unit_with_an_uncertain_result (tests.test_tl_job.SupervisorFailureTest.test_failure_after_the_spawn_still_ends_the_unit_with_an_uncertain_result) ... ok
test_wait_reads_a_supervisor_gone_without_a_result_as_indeterminate (tests.test_tl_job.SupervisorFailureTest.test_wait_reads_a_supervisor_gone_without_a_result_as_indeterminate) ... ok

----------------------------------------------------------------------
Ran 3 tests in 3.201s

OK
```

Código de saída: `0`. O primeiro caso injeta `OSError(28, "no space left on device")` em
`write_status` **somente** no estado `running`, depois de o neto real já ter provado que está
vivo (ele espera o arquivo `spawned.txt`): é falha *após* o spawn, não antes. Ele afirma saída
`0` do `supervise`, `result.json` existindo, `state: crashed`, `effects: uncertain`, detalhe
citando `no space left` e `failed internally`, `supervisor_liveness` igual a `gone`, e que o
arquivo do neto **para de crescer** ao longo de 2 s — a unidade não sobreviveu ao supervisor. Em
seguida chama o `wait` pela CLI e afirma saída `5` com `effects: uncertain` e sem `outcome`.

O segundo caso é o caminho **sem `result.json` com supervisor encerrado**: lease livre, `wait`
com prazo de 30 s e `LEASE_GRACE_SECONDS` reduzido a 0,2 s, afirmando saída `5`,
`state: indeterminate`, `effects: uncertain`, retorno em menos de 10 s — o que distingue
"reconheceu o supervisor encerrado" de "esperou o prazo" — e que nenhum `result.json` foi
inventado. Ele é `skipUnless(tl_job.LEASE_SUPPORTED)`, porque sem a primitiva a liveness é
`unknown` por desenho. O terceiro caso guarda o outro lado: lease **detido** lê `alive`, um
segundo `claim_lease` no mesmo arquivo devolve `busy`, e só depois do `release()` a leitura vira
`gone`.

Contraprova de que o comportamento vizinho continua verde:

```
python -m unittest tests.test_tl_job.FailureTest tests.test_tl_job.ContainmentTest tests.test_tl_job.StatePathTest tests.test_tl_job.IdentityTest
```

```
----------------------------------------------------------------------
Ran 19 tests in 27.137s

OK
```

Código de saída: `0`. E o compilador como portão mínimo do arquivo tocado:
`python -m py_compile scripts/tl_job.py` → sem saída, código `0`.

### Prova de discriminação por mutação

Cópia de `scripts/` e `tests/` em diretório temporário **fora** da árvore (removida depois, não
publicada, fora do manifesto), com a correção revertida por cirurgia de texto: sem o handler
`except Exception` de `run_supervised`, sem a varredura em `finally`, sem `containment.close()` e
sem o ramo de liveness do `wait`. Os auxiliares de lease ficaram no lugar, para o mutante falhar
pelo defeito e não por `AttributeError`. Comando literal — o arquivo de teste da cópia é
invocado direto porque ele resolve `SCRIPTS` em relação a si mesmo:

```
python "<tmp>/tests/test_tl_job.py" SupervisorFailureTest -v
```

Saída recortada nas linhas de asserção e no rodapé, literal:

```
OSError: [Errno 28] no space left on device
ResourceWarning: subprocess 29648 is still running
AssertionError: 4 != 5
----------------------------------------------------------------------
Ran 3 tests in 30.845s

FAILED (failures=1, errors=1)
```

Lido literalmente: na cópia anterior o `OSError` **escapa** do `supervise` (nenhum `result.json`,
nenhum estado terminal) e o processo filho **continua vivo** — é o `ResourceWarning` que mostra a
unidade órfã; e o caminho do `wait` devolve `4` (`wait_timeout`) depois dos 30 s inteiros, onde o
corrigido devolve `5`. O terceiro caso (lease detido) passa nas duas versões: os casos novos não
falham por construção.

### Limites desta rodada

- A suíte completa é portão do **condutor host** sobre a árvore final de cada rodada
  (`python scripts/validate_repository.py`, `python -m unittest discover -s tests -p test_*.py`,
  `git diff --check`), não deste papel. As saídas da árvore final desta rodada ficam registradas
  pelo host na seção de fechamento, depois da revisão independente. Aqui ficam apenas os casos
  dirigidos, com comando e saída literais.
- A verificação rodou em Windows, então o lease exercitado aqui é `msvcrt.locking`. O ramo
  `fcntl.flock` é exercitado pelo CI Linux; esse resultado ainda não existe nesta árvore porque
  este papel não faz commit nem push.
- O lease prova liveness pelo que o SO garante: a trava cai quando o processo termina, de
  qualquer forma. Ele **não** cobre sistema de arquivos de rede sem travamento confiável nem
  plataforma sem a primitiva — nesses casos a resposta é `unknown` e o `wait` mantém o
  comportamento antigo, por prazo, em vez de afirmar encerramento.
- A janela de carência significa que um supervisor morto é reconhecido **depois** de alguns
  segundos, não instantaneamente; é o preço de nunca ler um supervisor recém-nascido como morto.
- `effects: uncertain` é o que está afirmado quando a unidade pode ter rodado. Nenhum artefato
  desta rodada afirma que os efeitos parciais são conhecidos, e nenhum estado foi promovido.

## Adendo — varredura não provada e fronteira do `supervise` (rodada 12, 2026-09-11)

Dois achados do Checker foram corrigidos nesta rodada, na fronteira estrita apontada. Arquivos
tocados: `scripts/tl_job.py`, `tests/test_tl_job.py`, `docs/EXECUTION_PROTOCOL.md`, `CHANGELOG.md`
(entrada 0.8.0) e esta evidência. T001–T011 e o STATUS global não foram alterados, nenhum serviço,
dependência ou credencial entrou (biblioteca padrão), nenhum dado de consumidor foi importado, e
nenhum commit, tag ou push foi feito por este papel.

### Achado 1 — `swept: "unproven"` era lido como unidade entregue

A cadeia, confirmada por leitura do código antes de mexer: com `HAS_WAITID` falso, `watch` colhe o
líder por `process.wait()`; a varredura seguinte não tem identidade própria para sinalizar e devolve
`Sweep("unproven")` **sem** falha; `describe` grava `containment.swept: "unproven"` sem
`sweep_failed`; e o `classify` antigo, vendo estado `exited`, código `0` e payload admitido, devolvia
`('known', 0)`. Ou seja: o recibo afirmava unidade entregue exatamente no caso em que nada foi
provado encerrado.

Opção escolhida: **classificar como indeterminado**, não recusar antes de executar. `PROVEN_SCOPES`
passa a ser `("job_object", "process_group")` e `swept_proven` exige alcance provado; qualquer
`unproven` — com ou sem falha registrada — resulta em `effects: uncertain` e saída `5`, mesmo com
código zero e payload admitido. Recusar antes de executar apagaria um resultado que pode ser útil,
quando o que não se pode afirmar é só o fim da árvore. A opção está registrada no `CHANGELOG.md`
(0.8.0) e em `docs/EXECUTION_PROTOCOL.md`, seção `Contenção da árvore do job`.

Caso dirigido de comportamento, como o achado pediu: líder POSIX que cria um neto, o neto grava
`survivor-pid.txt` e bate em `survivor-beat.txt` por até 30 s, e o líder sai com `0`. Com
`HAS_WAITID` forçado a falso, o caso confere que o neto **está** vivo e ainda escrevendo (o tamanho
do batimento cresce) enquanto o resultado traz `state: exited`, `exit_code: 0`,
`outcome: delivered`, `swept: "unproven"`, sem `sweep_failed`, e ainda assim `effects: uncertain`
com o `wait` devolvendo `5`. O neto é encerrado pelo próprio pid no `cleanup`, e é autolimitado a
30 s para nunca sobreviver à suíte. O caso é **pulado no Windows** com a razão declarada
(`the process group branch only exists on POSIX; the Linux CI exercises this case`) — é o ramo de
grupo de processo, exercitado pelo Linux do workflow de validação. Para que a regra também fique
coberta onde se verificou, há um segundo caso que aciona `classify` direto e roda nas duas
plataformas, conferindo `unproven` → `('uncertain', 5)` e cada alcance de `PROVEN_SCOPES` →
`('known', 0)`.

### Achado 2 — `supervise` aceitava qualquer diretório e executava o manifesto encontrado nele

O subcomando público recebia `--job-dir` e, sem nenhuma verificação, lia o `manifest.json` dali e
executava o argv declarado: o limite de caminho de `start` (`check_state_dir`, `job_directory`) não
era reaplicado e o manifesto não era validado.

Opção escolhida: **manter o subcomando e refazer o limite**, porque é por ele que `command_start`
reentra no script destacado; remover a rota quebraria o despacho. `supervise` passa a receber
`--state-dir` e `--unit` (o `--job-dir` saiu da linha de comando), reaplica `check_state_dir` e
`job_directory` — componentes simples, job contido na árvore de estado, link resolvido por
`realpath` e recusado — e valida o manifesto inteiro antes de **qualquer** leitura de log ou
execução: lista fechada `MANIFEST_KEYS`, tipos, `schema`, `unit` coincidente com o pedido, `cwd` e
`result_file` dentro dos limites. Recusa levanta `JobError`, então `main` imprime recibo
`invalid_input` com `effects: none`.

Casos dirigidos, todos conferindo a recusa **junto com** a ausência de efeito (nenhum argv
executado, nenhum `stdout.log`, `stderr.log`, `result.json`, `status.json`, `supervisor.json` ou
lease criado nos diretórios envolvidos): diretório de job alcançado por link; diretório arbitrário
como diretório de estado; manifesto com campo que uma reivindicação real nunca carrega; manifesto de
outro schema; manifesto escrito para outra unidade; manifesto que aponta arquivo de resultado fora
das duas árvores; e a linha de comando não oferecendo mais diretório de job. O argv plantado em cada
caso criaria um arquivo marcador se fosse obedecido; o marcador nunca aparece. O caso do link usa
`symlink` e, quando a conta do Windows não tem o privilégio, cai para junction (`mklink /J`), que
`os.path.realpath` resolve igual — assim a fronteira foi exercitada de fato aqui, não só no Linux.

Controle positivo, sem o qual o conjunto não discriminaria nada: uma reivindicação real no próprio
diretório do job continua rodando (`state: exited`, `outcome: delivered`, `effects: known`, saída
`0`). Foi ele que pegou um defeito introduzido pela própria correção: `MANIFEST_KEYS` declarava
`schema` como `str` enquanto `SCHEMA_VERSION` é `1` (int), então **toda** reivindicação legítima era
recusada com "`schema` has the wrong type". Sem o controle positivo, os seis casos de recusa teriam
passado por um motivo errado.

### Comandos e saídas literais desta rodada

Em Windows, offline, a partir da raiz do pacote
(`E:/Documentos/ProjetosIA/Tl-Orchestrador/worktrees/token-efficiency-20260911`):

```
python -m unittest tests.test_tl_job.UnprovenSweepTest tests.test_tl_job.SupervisorBoundaryTest -v
...
Ran 10 tests in 3.364s

OK (skipped=1)
```

O `skipped=1` é o caso POSIX acima, com a razão impressa literal:
`skipped 'the process group branch only exists on POSIX; the Linux CI exercises this case'`.

Grupo dirigido mais amplo, para conferir que a vizinhança da contenção não regrediu:

```
python -m unittest tests.test_tl_job.UnprovenSweepTest tests.test_tl_job.SupervisorBoundaryTest
  tests.test_tl_job.ContainmentTest tests.test_tl_job.SweepFailureTest
  tests.test_tl_job.SweepFailureReportTest tests.test_tl_job.SupervisorFailureTest
s......................
----------------------------------------------------------------------
Ran 23 tests in 20.006s

OK (skipped=1)
```

Portão mínimo dos arquivos tocados: `python -m py_compile scripts/tl_job.py tests/test_tl_job.py`
→ sem saída, código `0`.

E a rota removida, conferida direto na linha de comando:

```
python scripts/tl_job.py supervise --job-dir <qualquer diretório>
usage: tl_job.py supervise [-h] --state-dir STATE_DIR --unit UNIT
tl_job.py supervise: error: the following arguments are required: --state-dir, --unit
```

### Prova de discriminação por mutação

Cópia de `scripts/` e `tests/` em diretório temporário **fora** do repositório (não publicada, fora
do manifesto), com cada correção revertida por cirurgia de texto, uma por vez.

Mutação do achado 1 — `PROVEN_SCOPES = ("job_object", "process_group", "unproven")`, a leitura
antiga. Comando e saída recortada, literais:

```
python "<tmp>/tests/test_tl_job.py" UnprovenSweepTest -v
AssertionError: Tuples differ: ('known', 0) != ('uncertain', 5)
----------------------------------------------------------------------
Ran 2 tests in 0.007s

FAILED (failures=1, skipped=1)
```

Mutação do achado 2 — `--job-dir` devolvido ao parser e a rota antiga reconstruída (`read_json` do
manifesto encontrado, nenhuma verificação, direto para `run_supervised`). Um sondador plantou um
manifesto bem formado em um diretório qualquer fora de qualquer árvore de estado, com argv que grava
um marcador, e chamou a rota antiga:

```
python -m unittest -v tests.test_probe_r2   (na cópia, fora do repositório)
Ran 1 test in 0.343s
OK
exit: 0
marker created: True
files left outside the tree: ['manifest.json', 'result.json', 'status.json', 'stderr.log',
'stdout.log', 'supervisor.json', 'supervisor.lock']
```

Lido literalmente: a forma anterior obedecia o argv plantado e escrevia o conjunto inteiro de
arquivos do supervisor fora da árvore; a forma corrigida recusa antes de ler, com `invalid_input` e
`effects: none`. A cópia mutante fica fora do repositório e não entra em commit algum.

### Limite honesto desta correção

O que o achado 2 fecha é a reentrada do próprio método: nenhum campo de manifesto é obedecido sem
validação, nenhum caminho escapa da árvore de estado nomeada e link é recusado. O que ele **não**
pode fechar é a permissão do sistema de arquivos: quem consegue escrever um manifesto bem formado
dentro de um diretório de estado que o consumidor escolheu expor, e chama `supervise` apontando para
ele, ainda tem esse manifesto executado — é a mesma autoridade de quem poderia chamar `start`. Isso
está dito em `docs/EXECUTION_PROTOCOL.md` e não é afirmado como resolvido.

### Fechamento — portões da árvore final (registrado pelo condutor host)

A suíte completa é portão do condutor host sobre a árvore final de cada rodada, não deste papel:
`python scripts/validate_repository.py`, `python -m unittest discover -s tests -p test_*.py` e
`git diff --check`. O último resultado registrado pelo host é o da árvore final da rodada 11: os
três portões passaram, saída `0`, `Ran 66 tests`, `OK`, `skipped=1`, 324 s, em Windows. As saídas da
árvore final desta rodada 12 são anotadas aqui pelo host depois da revisão independente; este papel
não as afirma.

## Adendo — o resultado admitido fica preso à execução (rodada 13, 2026-09-11)

Achado R1 da rodada 13 (`scripts/tl_job.py:392`): `admit_result` lia qualquer JSON já presente em
`result_file`, e nada no payload nomeia a execução que o escreveu. Reutilizando o mesmo
`--result-file`, uma unidade nova que saísse com zero sem tocar em `TL_JOB_RESULT` herdava o
`delivered`/`ready_for_delivery` da anterior.

Das duas opções oferecidas, a escolhida foi **recusar antes do spawn um `result_file` que já
existe**. Emitir um token de identidade no spawn exigiria que o papel o devolvesse dentro do payload
— mudança de contrato para todo condutor acoplado — sem garantia maior: a ausência antes do spawn já
prende o arquivo a esta execução, porque o que for lido depois apareceu enquanto ela rodava. Um
caminho que nem pode ser inspecionado é recusado do mesmo jeito; supor que está ausente é exatamente
o sucesso herdado que a guarda existe para recusar. A recusa vive em `execute_unit`, o único lugar
que despacha e admite, e não em `command_start`: lá, antes do `mkdir`, ela quebraria a idempotência
(um `start` repetido legítimo, com o mesmo manifesto e o resultado já escrito, seria recusado em vez
de reaproveitar). O recibo da recusa é `state: start_failed`, `effects: none`, sem `outcome`, saída
`6`. Registrado em `docs/EXECUTION_PROTOCOL.md` (linha do `result_file` e regra do acoplamento) e no
CHANGELOG 0.8.0.

### Caso dirigido, rodado antes de qualquer suíte

Em Windows, offline, a partir da raiz do pacote. O caso pré-cria um sucesso permitido em
`receipts/T012-1.json`, despacha uma unidade nova que só escreve um sentinela e sai com zero, e exige
recusa explícita; o par positivo prova que a guarda não fecha o uso legítimo de `--result-file`:

```
python -m unittest tests.test_tl_job.InheritedResultTest -v
test_a_result_file_that_the_unit_itself_creates_is_still_admitted ... ok
test_a_success_left_at_the_result_file_is_never_inherited_by_a_new_unit ... ok
Ran 2 tests in 1.409s

OK
```

Vizinhança dirigida, para conferir que identidade, falhas, entrada, fronteira do `supervise` e lista
de campos permitidos não regrediram:

```
python -m unittest tests.test_tl_job.IdentityTest tests.test_tl_job.FailureTest
  tests.test_tl_job.InputTest tests.test_tl_job.SupervisorBoundaryTest
  tests.test_tl_job.ReportAllowlistTest
Ran 43 tests in 214.428s

OK (skipped=1)
```

### Prova de discriminação por mutação

Cópia de `scripts/` e `tests/` em diretório temporário **fora** do repositório (não publicada, fora
do manifesto), com a guarda removida por cirurgia de texto (o bloco `unbound = unbound_result(...)`
no topo de `execute_unit`, 430 caracteres). O mesmo caso dirigido, na cópia mutante:

```
python -m unittest tests.test_tl_job.InheritedResultTest -v   (na cópia, fora do repositório)
AssertionError: 0 == 0 : a result from an earlier unit must never answer as success
Ran 2 tests in 1.443s

FAILED (failures=1)
```

E o mesmo despacho conduzido à mão nas duas árvores, para ler o recibo inteiro:

```
mutante (sem a guarda):  wait exit 0 | state exited       | outcome delivered | effects known
                         | result_status admitted
árvore corrigida:        wait exit 6 | state start_failed  | outcome None      | effects none
                         | result_status absent
```

Lido literalmente: sem a guarda, uma unidade que não escreveu nada devolve `delivered` com saída
zero; com ela, devolve recusa explícita e nenhum efeito. A cópia mutante fica fora do repositório e
não entra em commit algum.

### Limite honesto desta rodada

A guarda prende o arquivo à execução por ausência prévia, não por identidade criptográfica: quem
puder escrever no `result_file` **enquanto** a unidade roda ainda entrega o payload que quiser — é a
mesma autoridade de quem despacha a unidade. O que fica fechado é a herança entre execuções, que era
o achado. Não há verificação de reexecução de `supervise` sobre uma reivindicação que já tem
`result.json` terminal; isso estava fora do escopo de R1 e não é afirmado como resolvido.

### Fechamento — portões da árvore final (registrado pelo condutor host)

A suíte completa continua sendo portão do condutor host sobre a árvore final de cada rodada, não
deste papel: `python scripts/validate_repository.py`,
`python -m unittest discover -s tests -p test_*.py` e `git diff --check`. O último resultado
registrado pelo host é o da árvore final da rodada 12: os três portões passaram, saída `0`,
`Ran 76 tests`, `OK`, `skipped=2`, em Windows. As saídas da árvore final desta rodada 13 são anotadas
aqui pelo host depois da revisão independente; este papel não as afirma.

## Adendo — nada lido do disco chega à execução ou ao recibo sem guarda (rodada 14, 2026-09-11)

Três achados do Checker `dedfadbf` sobre a mesma classe: conteúdo lido do disco alcançando execução
ou recibo sem validação. O adendo da rodada 13 já registrava o primeiro deles como limite explícito
("Não há verificação de reexecução de `supervise` sobre uma reivindicação que já tem `result.json`
terminal; isso estava fora do escopo de R1 e não é afirmado como resolvido"); esta rodada o fecha.

- **R1 — unidade terminada nunca é reaberta** (`scripts/tl_job.py`, `supervise`). Depois de
  `check_manifest` e **antes** de `claim_lease` e do despacho, a existência de `result.json` recusa
  com `conflict`, `effects: none` e saída `3`, sem tocar em nada no disco. A checagem é a existência
  do arquivo terminal, não seu conteúdo: resultado corrompido ou truncado recusa igual, porque só
  uma execução pode responder por uma unidade.
- **R2 — um só gate de manifesto para todos os leitores** (`load_claim`). O `validate_claim` que
  `supervise` já usava passa a valer para reentrada de `start`, `status`, `wait` e `result`:
  conjunto exato de chaves, tipo por chave (`bool` recusado como inteiro), versão de schema, unidade
  correspondente, impressão de 16 hexadecimais, limites de `argv`, `timeout`, `cwd`/`result_file`
  absolutos e dentro do teto de bytes. Manifesto ausente, divergente ou não computável responde
  `JobError` compacto em JSON — nunca traceback — sem reaproveitar resultado e sem executar.
- **R3 — campo de disco cortado antes de virar recibo** (`locators`, `current_state`,
  `enforce_ceiling`). Localizadores são cortados por bytes (`MAX_FIELD_BYTES`, `NAME_BYTES`), estado
  gravado fora da lista fechada `KNOWN_STATES` vira `unknown`, e `enforce_ceiling` respeita
  `--max-bytes` inclusive ao reduzir aos `CORE_KEYS`, caindo para um recibo mínimo marcado
  `clipped` em vez de estourar o teto.

Varredura da classe comum dentro destes arquivos, atrás de outro leitor de estado sem o mesmo
guarda: `supervisor_liveness` não lê conteúdo de arquivo; o estado que o `JobError` de `report`
carrega vem do `current_state` já limitado; `rebuild_result` continua inteiramente por lista de
campos permitidos. Nenhum leitor sem guarda restou. `docs/EXECUTION_PROTOCOL.md` descreve o contrato
implementado; uma imprecisão foi corrigida lá: o conjunto aceito **do disco** é apenas `starting`,
`running`, `exited`, `timeout`, `crashed`, `start_failed`, e não a lista inteira de estados de
transporte.

### Casos dirigidos, rodados antes de qualquer suíte

Em Windows, offline, a partir da raiz do pacote. Dez casos novos em três classes —
`FinishedUnitTest` (R1), `ClaimValidationTest` (R2) e `ReceiptCeilingTest` (R3):

```
python -m unittest tests.test_tl_job.FinishedUnitTest tests.test_tl_job.ClaimValidationTest
  tests.test_tl_job.ReceiptCeilingTest
Ran 10 tests in 3.628s

OK
```

Vizinhança dirigida, para conferir que identidade, fronteira do `supervise`, teto do recibo e
caminhos de estado não regrediram:

```
python -m unittest tests.test_tl_job.IdentityTest tests.test_tl_job.SupervisorBoundaryTest
  tests.test_tl_job.ReceiptLimitsTest tests.test_tl_job.StatePathTest
Ran 21 tests in 12.580s

OK
```

### Prova de discriminação por mutação

Cópia de `scripts/` e `tests/` em diretório temporário **fora** do repositório (não publicada, fora
do manifesto). Uma mutação por achado, cada uma sobre a cópia restaurada ao original; controle antes
e depois: `Ran 10 tests in 3.694s`, `OK`.

R1, com a guarda desarmada (`if os.path.lexists(job_dir / "result.json"):` → `if False:`):

```
python -m unittest tests.test_tl_job.FinishedUnitTest   (na cópia, fora do repositório)
FAIL: test_a_second_supervision_of_a_finished_unit_changes_nothing_on_disk
AssertionError: b'{"a[69 chars]hed":false,"kind":"none","unit_ran":false},"de[410 chars]"}\n'
             != b'{"a[69 chars]hed":true,"kind":"windows_job_object","swept":[357 chars]"}\n'
Ran 1 test in 0.536s

FAILED (failures=1)
```

Lido literalmente, e com a honestidade que a mutação exige: na segunda supervisão simples o mutante
**não** reexecuta o argv, porque a guarda da rodada 13 (`unbound_result`) recusa o `--result-file`
já existente; o que ele faz é sobrescrever o único arquivo terminal com um registro `start_failed`.
A perda é essa — a resposta da unidade desaparece. Removendo antes o `unit-result.json` nomeado pela
reivindicação, a mesma cópia mutante volta a executar de verdade:

```
AssertionError: 'ran\nran\n' != 'ran\n'
  ran
- ran
 : the second supervision ran the unit again
Ran 1 test in 0.711s

FAILED (failures=1)
```

R2, com o gate central desarmado (`return validate_claim(manifest, unit)` → `return manifest` em
`load_claim`):

```
python -m unittest tests.test_tl_job.ClaimValidationTest   (na cópia, fora do repositório)
AssertionError: 0 != 2   (status)      AssertionError: 4 != 2   (wait)
AssertionError: 5 != 2   (result)
test_reentering_start_over_a_broken_claim_refuses_instead_of_reusing_it:
  the command answered with a traceback instead of a receipt
  KeyError: 'cwd'  em manifest_fingerprint (tl_job.py:380), a partir de command_start:1413
Ran 6 tests in 17.669s

FAILED (failures=11)
```

Lido literalmente: sem o gate, cada leitor falha do seu jeito — um responde sucesso sobre uma
reivindicação quebrada, outros trocam o erro de uso por timeout ou por falha de unidade, e a
reentrada de `start` devolve traceback em vez de recibo. A cópia mutante fica fora do repositório e
não entra em commit algum.

### Limite honesto desta rodada

R1 prende a unidade ao arquivo terminal por existência, não por identidade: quem apagar
`result.json` à mão recupera uma unidade executável — é a mesma autoridade de quem despacha. R2
valida a forma e a fronteira da reivindicação, não a intenção de quem a escreveu: manifesto bem
formado dentro de um diretório de estado exposto continua sendo obedecido, como já dito no adendo da
rodada 12. R3 limita o que o recibo carrega, não o que fica gravado no disco. As mutações acima
foram as únicas rodadas, e cobrem R1 e R2; R3 é sustentado pelos casos dirigidos com estado e
`result_file` enormes, não por mutação. Nenhuma medição de custo em tokens é afirmada nesta rodada.

### Fechamento — portões da árvore final (registrado pelo condutor host)

A suíte completa continua sendo portão do condutor host sobre a árvore final de cada rodada, não
deste papel: `python scripts/validate_repository.py`,
`python -m unittest discover -s tests -p test_*.py` e `git diff --check`. O último resultado
registrado pelo host é o da árvore final da rodada 13: os três portões passaram, saída `0`,
`Ran 78 tests`, `OK`, `skipped=2`, em Windows. As saídas da árvore final desta rodada 14 são
anotadas aqui pelo host depois da revisão independente; este papel não as afirma.

## Adendo — sucesso terminal só depois do fim comprovado (rodada 15, 2026-09-11)

Dois achados do Checker sobre a mesma entrega. O primeiro é comportamental: a unidade podia forjar
um `result.json` válido no diretório da própria unidade e `wait`/`result` o devolviam como sucesso
terminal enquanto o processo ainda escrevia. O segundo é de registro: a prova publicada descrevia
uma árvore de testes que não existe mais.

### O que a correção faz

A raiz do primeiro achado é que **todo** campo do registro terminal é recomputável por quem lê o
`manifest.json` — impressões do manifesto e da autorização inclusive. O arquivo sozinho, portanto,
não diz quem o escreveu nem quando. A guarda não tenta adivinhar autoria; ela pergunta pelo
supervisor, com o mesmo recurso que já provava liveness:

- `termination_proof(job_dir)` responde `proven`, `running`, `unproven` ou `unsupported` a partir da
  trava exclusiva `supervisor.lock` — `running` enquanto a trava estiver tomada, `proven` quando ela
  puder ser adquirida sobre um lease que existiu, `unproven` quando nenhum lease chegou a existir e
  `unsupported` onde a plataforma não tem trava exclusiva de arquivo.
- `proven_termination(job_dir, settle=TERMINATION_SETTLE_SECONDS)` (`scripts/tl_job.py:1040`) repete
  a pergunta apenas enquanto a resposta for `running`, limitada por `TERMINATION_SETTLE_SECONDS =
  2.0`. É a janela entre a escrita do registro terminal pelo `finalize` e a saída real do processo;
  nenhum outro estado é esperado.
- `report` recusa com `indeterminate`, `effects: uncertain` e saída `5` enquanto a prova for
  `running` ou `unproven`, e declara o campo `termination` no recibo sempre que o fim não pôde ser
  provado. O laço do `wait` deixou de quebrar na existência do arquivo: quebra no arquivo **mais**
  um supervisor que já não está vivo; com a trava tomada, ele segue esperando até o `timeout`.
- Além do fim, a forma conta. `rebuild_result` exige todas as chaves de `REQUIRED_RESULT_KEYS`
  (`scripts/tl_job.py:64-67`) — `schema`, `job_id`, `unit`, `state`, `effects`, `exit_code`,
  `started_at`, `finished_at`, `authorization_fingerprint`, `manifest_fingerprint`, `logs`,
  `result_status`. Registro mais curto é indeterminado, não entrega.

`docs/EXECUTION_PROTOCOL.md` e o `CHANGELOG.md` descrevem esse contrato, incluindo o limite honesto
abaixo.

### Casos dirigidos, rodados antes de qualquer suíte

Em Windows, offline, a partir da raiz do pacote. A classe nova é `ForgedTerminalResultTest`, três
casos, sendo o primeiro o teste negativo pedido: a unidade lê o manifesto, grava um `result.json`
aparentemente válido e continua escrevendo; `wait` responde `timeout` (saída `4`) e `result`
responde `indeterminate` com `effects: uncertain` (saída `5`) enquanto o processo não termina.

```
python -m unittest tests.test_tl_job.ForgedTerminalResultTest -v
test_a_record_shorter_than_this_supervisor_writes_is_not_a_delivery ... ok
test_neither_wait_nor_result_delivers_while_the_forging_unit_keeps_writing ... ok
test_the_same_unit_is_delivered_once_it_has_really_ended ... ok

Ran 3 tests in 9.938s

OK
```

Vizinhança dirigida, para conferir que resultado herdado, varredura não provada, falha do
supervisor, unidade terminada, lista de campos do recibo e caminhos de estado não regrediram:

```
python -m unittest tests.test_tl_job.InheritedResultTest tests.test_tl_job.UnprovenSweepTest
  tests.test_tl_job.SupervisorFailureTest tests.test_tl_job.FinishedUnitTest
  tests.test_tl_job.ReportAllowlistTest tests.test_tl_job.StatePathTest
Ran 18 tests in 13.140s

OK (skipped=1)
```

O `skipped=1` é `test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered`, que só
existe em POSIX (`@unittest.skipIf(os.name == "nt", POSIX_ONLY)`); o CI Linux o exercita.

### Prova de discriminação por mutação

Cópia de `scripts/` e `tests/` em diretório temporário **fora** do repositório (não publicada, fora
do manifesto), restaurada ao original antes de cada mutação. Quatro mutantes, com controle antes e
depois: `Ran 3 tests in 9.672s`, `OK`, saída `0`, e ao final `Ran 3 tests in 9.718s`, `OK`, saída
`0`.

Mutante 1 — guarda inteira removida (gate de prova do `report` trocado por `proof = "proven"`,
condição do `wait` de volta à existência do arquivo, checagem de completude apagada):

```
FAIL: test_neither_wait_nor_result_delivers_while_the_forging_unit_keeps_writing
AssertionError: 0 == 0 : {... 'effects': 'known', 'exit_code': 0, 'outcome': 'delivered',
  'result_status': 'admitted', 'state': 'exited', ...}
AssertionError: 0 != 4 : {... 'outcome': 'delivered' ...}   (wait)
Ran 3 tests in 4.644s

FAILED (failures=6)
```

Lido literalmente: sem a guarda, o recibo da unidade que ainda está escrevendo sai `outcome:
delivered`, `effects: known`, `exit_code: 0` — exatamente o defeito apontado.

Mutante 2 — só o gate de prova do `report`:

```
AssertionError: 0 != 5 : {... 'outcome': 'delivered', 'effects': 'known' ...}
Ran 3 tests in 7.653s

FAILED (failures=2)
```

Mutante 3 — só a condição do `wait` revertida para existência de arquivo. O `wait` passa a devolver
o que o `result` já recusa, e a recusa aparece no lugar do `timeout`:

```
AssertionError: 5 != 4 : {'effects': 'uncertain', 'error': 'a terminal result is on disk while the
  supervisor of this unit is still running; nothing written so far is final', 'state': 'running'}
Ran 3 tests in 8.754s

FAILED (failures=1)
```

Mutante 4 — só a checagem de completude de `rebuild_result`. Um registro sem `logs`, gravado depois
do fim comprovado, volta a ser entregue:

```
FAIL: test_a_record_shorter_than_this_supervisor_writes_is_not_a_delivery (missing='logs')
AssertionError: 0 != 5 : {... 'outcome': 'delivered', 'result_status': 'admitted' ...}
Ran 3 tests in 9.667s

FAILED (failures=3)
```

Os quatro mutantes falham e os dois controles passam: o teste discrimina a guarda, e não apenas a
presença do arquivo. A cópia mutante fica fora do repositório e não entra em commit algum.

### Limite honesto desta rodada

A prova é sobre o supervisor, não sobre o disco. Uma unidade que roda com o mesmo usuário continua
podendo escrever no diretório da unidade, inclusive depois que o supervisor sai; o que esta rodada
promete é que nenhuma leitura terminal é aceita enquanto o supervisor daquela unidade estiver
provadamente vivo, e que o registro aceito tem a forma completa que só o `finalize` produz. Onde não
existe trava exclusiva de arquivo não há prova possível: o recibo declara `termination:
"unsupported"` e `ForgedTerminalResultTest` é pulado inteiro
(`@unittest.skipUnless(tl_job.LEASE_SUPPORTED, ...)`) — nesta árvore, em Windows, ele **não** está
entre os dois pulados da suíte. `TERMINATION_SETTLE_SECONDS = 2.0` é uma janela finita: uma saída de
processo que demore mais que isso depois da escrita terminal responde `indeterminate` em vez de
entregar, que é o lado seguro do erro. Nenhuma medição de custo em tokens é afirmada nesta rodada.

### Fechamento — os três portões desta revisão final

Executados depois da correção de R1, sobre esta árvore, em Windows, offline. Uma passagem completa,
nenhuma reaproveitada de rodada anterior — a passagem de 78 testes da rodada 13, citada no adendo
anterior, descreve aquela árvore e não esta.

```
python scripts/validate_repository.py
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
(saída 0)
```

```
python -m unittest discover -s tests -p "test_*.py"
.....................................s...................................................s.
----------------------------------------------------------------------
Ran 91 tests in 339.380s

OK (skipped=2)
(saída 0)
```

São os 91 casos da árvore atual, em 20 classes. Os dois pulos são os mesmos já justificados: o de
privilégio de link simbólico nesta sessão Windows e
`test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered`, que só existe em POSIX
e é exercitado pelo CI Linux. `ForgedTerminalResultTest` **não** está entre eles: nesta plataforma há
trava exclusiva de arquivo, e os três casos rodaram.

```
git diff --check
(sem saída, saída 0)
```

Limite deste portão, o mesmo de sempre e declarado de novo: `git diff --check` só enxerga arquivo já
rastreado, e `scripts/tl_job.py`, `tests/`, `docs/EXECUTION_PROTOCOL.md` e os dois artefatos em
`_tl-orc/project/` ainda aparecem como `??` em `git status --porcelain` — este papel não faz
`git add`. Esses arquivos foram conferidos por busca direta de espaço em branco ao fim de linha
(`[ 	]+$`), com zero ocorrências.

Ordem real desta revisão: casos dirigidos, depois mutação em cópia isolada, depois os três portões
e, por último, a transcrição das saídas nestes dois artefatos de registro — `validate_repository.py`
e `git diff --check` foram repetidos depois da transcrição, com o mesmo resultado, e nenhuma
alteração posterior tocou `scripts/`, `tests/`, `docs/` ou o manifesto.

## Adendo — fim improvável, reivindicação ilegível e lease ocupado (rodada 16, 2026-09-11)

Três achados do Checker sobre a mesma entrega, todos em `scripts/tl_job.py`: uma brecha que ainda
deixava entregar sem prova de fim, uma classificação errada de manifesto ilegível e uma recusa sem
recibo. Os três são comportamentais e os três ganharam caso dirigido e mutante.

### O que cada correção faz

**R1 — `unsupported` não entrega.** A rodada anterior fechou `running` e `unproven`, mas o gate
comparava contra dois estados e deixava `unsupported` passar: em plataforma sem trava exclusiva de
arquivo, um `result.json` plantado continuava saindo como `outcome: delivered`, `effects: known`,
`exit_code: 0` — exatamente o fim que ninguém observou. O gate de `report` passou a ser positivo,
`if proof != "proven"`, então só a prova afirmativa entrega. `UNPROVABLE_END` traduz `unproven` e
`unsupported` em suas razões escritas, e a recusa sai como `indeterminate`, `effects: uncertain`,
saída `5`, com o campo `termination` nomeando qual fim não pôde ser provado. `wait`, `result` e o
relatório interno passam pelo mesmo caminho, então nenhum leitor tem uma porta própria.

**R2 — manifesto ilegível é `invalid_input`, não reivindicação concorrente.** A reivindicação chega
por rename, então só o nome que **ainda não existe** é esperado pela janela curta de concorrência.
Um arquivo presente que não se lê como reivindicação nunca vai virar uma. `read_claim_file(path,
limit=MAX_RESULT_BYTES)` devolve um par `(razão, dados)` separando o ausente (`"absent"`) do
presente e inutilizável — acima do teto de bytes, texto que não é UTF-8, JSON inválido, erro de
leitura ou raiz que não é objeto. O laço de `load_claim` recusa qualquer razão diferente de
`"absent"` na primeira volta, com `invalid_input`, `effects: none` e saída `2`; só o ausente segue
sendo esperado por `CLAIM_WAIT_SECONDS`. Vale igual para `status`, `wait`, `result` e a reentrada de
`start`, que é o que a seção de manifesto ilegível do protocolo já prometia.

**R3 — `supervise` ocupado responde recibo.** O ramo de lease ocupado devolvia `EXIT_CONFLICT` nu.
`supervise` é alcançável pela linha de comando, então um código de saída sozinho é parada silenciosa
para quem lê stdout. Agora ele levanta `JobError(EXIT_CONFLICT, "conflict", …, effects="none")`, e o
recibo compacto sai pelo mesmo caminho de `main` que já publica toda outra recusa, sujeito ao mesmo
teto de bytes.

`docs/EXECUTION_PROTOCOL.md` e o `CHANGELOG.md` descrevem os três contratos, incluindo o limite
honesto abaixo.

### Casos dirigidos, rodados antes de qualquer suíte

Em Windows, offline, a partir da raiz do pacote. Três classes novas, treze casos, cada uma rodada
sozinha antes de qualquer suíte.

`UnprovableTerminationTest` força `LEASE_SUPPORTED = False` no processo com o registro terminal
forjado já no disco, e cobre os dois leitores mais o contraste com a prova possível:

```
python -m unittest tests.test_tl_job.UnprovableTerminationTest
Ran 4 tests in 0.277s

OK
```

`MalformedClaimTest` cobre `status`, `wait`, `result` e a reentrada de `start` sobre cada forma de
manifesto ilegível, mais os dois controles que preservam o comportamento antigo onde ele estava
certo — o ausente ainda é esperado como reivindicação concorrente, e a reivindicação que estava
sendo escrita ainda é lida quando aterrissa:

```
python -m unittest tests.test_tl_job.MalformedClaimTest
Ran 7 tests in 3.310s

OK
```

`BusyLeaseSuperviseTest` segura o lease e invoca `supervise` pela linha de comando, depois libera o
lease e invoca a mesma linha:

```
python -m unittest tests.test_tl_job.BusyLeaseSuperviseTest
Ran 2 tests in 6.027s

OK
```

### Prova de discriminação por mutação

Cada mutante em um diretório temporário **novo**, fora do repositório, criado com `tempfile.mkdtemp`
e removido com `shutil.rmtree` a partir de Python; a cópia leva só `scripts/` e `tests/`, não é
publicada e não entra em manifesto algum. Cada mutação é uma substituição de âncora única — o
condutor aborta se a âncora não aparecer exatamente uma vez — sobre uma cópia limpa.

Mutante 1 — o gate de `report` volta a aceitar `unsupported` (`if proof != "proven":` →
`if proof == "unproven":`):

```
python -m unittest tests.test_tl_job.UnprovableTerminationTest.test_an_unsupported_proof_delivers_no_terminal_result_to_any_reader
Ran 1 test in 0.083s

FAILED (failures=2)
```

As duas falhas são os dois subcasos, `command='result'` e `command='wait'`, ambas com
`AssertionError: 0 == 0` e o recibo trazendo `'effects': 'known'`, `'exit_code': 0`, `'outcome':
'delivered'`, `'state': 'exited'`, `'result_status': 'admitted'`, `'transport_only': True` — o
`delivered`/`known`/`0` que o achado descreve, reproduzido.

Mutante 2 — a recusa do manifesto ilegível sai de `load_claim` (as duas linhas
`if reason != "absent": refuse_manifest(reason)` removidas):

```
python -m unittest tests.test_tl_job.MalformedClaimTest
Ran 7 tests in 88.920s

FAILED (failures=17)
```

Cada falha é a classificação errada do achado, com a espera de volta no caminho (88,9 s contra 3,3 s
na árvore corrigida):

```
AssertionError: 3 != 2 : {"effects":"uncertain","error":"an incomplete claim already holds this
unit; inspect the state directory by hand","job_id":"T012","schema":1,"state":"conflict",
"unit":"T012"}
```

Mutante 3 — o ramo de lease ocupado volta ao código de saída nu (`return EXIT_CONFLICT` no lugar do
`raise JobError`):

```
python -m unittest tests.test_tl_job.BusyLeaseSuperviseTest.test_supervise_over_a_held_lease_answers_a_conflict_receipt
Ran 1 test in 5.408s

FAILED (failures=1)
AssertionError: '' is not true : the busy path stopped with a bare exit code and no receipt; stderr=
```

### Limite honesto desta rodada

R1 fecha a entrega sem prova, não cria prova onde ela não existe: em plataforma sem trava exclusiva
de arquivo o supervisor continua sem poder demonstrar que terminou, e a resposta honesta passa a ser
`indeterminate` em vez de um sucesso inventado — quem depende dessa plataforma perde a leitura
terminal, que é o lado seguro do erro. `UnprovableTerminationTest` roda em qualquer plataforma
porque força `LEASE_SUPPORTED` no processo; os dois casos de `BusyLeaseSuperviseTest` e o contraste
`test_the_same_record_is_delivered_where_the_ending_can_be_proven` dependem da trava real e são
pulados onde ela não existe — nesta árvore, em Windows, eles **não** estão entre os dois pulados da
suíte. R2 classifica o que está escrito no arquivo no instante da leitura; um manifesto que fica
válido depois da recusa exige nova invocação, de propósito. R3 promete o recibo na recusa por lease
ocupado, não exclusão mútua nova: a trava exclusiva é a mesma de antes. Nenhuma medição de custo em
tokens é afirmada nesta rodada; as medidas disponíveis continuam sendo bytes sintéticos de um
cenário controlado.

### Fechamento — os três portões desta revisão final

Executados depois das correções de R1, R2 e R3, sobre esta árvore, em Windows, offline. Uma única
passagem completa da suíte, nenhuma reaproveitada: a passagem de 91 testes da rodada 15, citada no
adendo anterior, descreve aquela árvore e não esta.

```
python -m unittest discover -s tests -p "test_*.py"
Ran 104 tests in 351.330s

OK (skipped=2)
(saída 0)
```

São os 104 casos da árvore atual, em 23 classes — os 91 da rodada anterior mais os treze desta. Os
dois pulos são os mesmos já justificados:
`test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused`, por privilégio de link
simbólico nesta sessão Windows, e
`test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered`, que só existe em POSIX
e é exercitado pelo CI Linux. As três classes novas rodaram inteiras.

```
python scripts/validate_repository.py
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
(saída 0)
```

```
git diff --check
(sem saída, saída 0)
```

Limite deste portão, o mesmo de sempre e declarado de novo: `git diff --check` só enxerga arquivo já
rastreado, e `scripts/tl_job.py`, `tests/`, `docs/EXECUTION_PROTOCOL.md` e os dois artefatos em
`_tl-orc/project/` ainda aparecem como `??` em `git status --porcelain` — este papel não faz
`git add`. Esses cinco caminhos foram conferidos por busca direta de espaço em branco ao fim de
linha (`[ \t]+$`), com zero ocorrências em cada um.

Ordem real desta revisão: os três conjuntos de casos dirigidos rodando sozinhos, depois as três
mutações em cópias isoladas fora do repositório, depois a passagem única da suíte, depois
`validate_repository.py` e `git diff --check`, e por último a transcrição das saídas nestes dois
artefatos de registro. Nenhuma alteração posterior tocou `scripts/`, `tests/`, `docs/` ou o
manifesto; as edições feitas depois dos portões são só de registro (`CHANGELOG.md`, esta evidência e
a Task), e `CHANGELOG.md` é arquivo rastreado, coberto pelo `git diff --check` repetido ao final com
o mesmo resultado.

### Portão `job-tests` da revisão final: corrida no arranjo do teste

O que falhou. O portão `job-tests` da revisão final desta rodada 16, executado pelo host em
21:29-21:35 em Windows sob carga, terminou com 1 erro em 104 testes (2 pulados):

```
ERROR: test_failure_after_the_spawn_still_ends_the_unit_with_an_uncertain_result (test_tl_job.SupervisorFailureTest...)
  File "tests/test_tl_job.py", line 1251, in test_failure_after_the_spawn_still_ends_the_unit_with_an_uncertain_result
    first = beat.stat().st_size
FileNotFoundError: [WinError 2] ...\tl-job-test-oy4ws9v6\work\beat.txt
Ran 104 tests in 346.172s
FAILED (errors=1, skipped=2)
```

A causa. É o arranjo do teste, não o supervisor. `refuse_the_running_status` só esperava
`spawned.txt` antes de levantar o `OSError(28)` no primeiro status `running`; `spawned.txt` é o
primeiro arquivo que `heartbeat.py` escreve e o `beat.txt` vem depois. O supervisor então derruba a
árvore corretamente, e sob carga isso acontecia antes do primeiro beat existir. A pré-condição
`beat.stat()` explodia com `FileNotFoundError` em vez de provar coisa alguma — o caso nunca chegava
a exercitar o comportamento que ele existe para exercitar. Nada no supervisor mudou e nada nele
precisa mudar: o próprio erro mostra a árvore sendo terminada rápido demais para o arranjo, que é o
comportamento desejado.

O que mudou no teste. Somente `tests/test_tl_job.py`; `scripts/tl_job.py`, `docs/` e o manifesto não
foram tocados nesta rodada. Um auxiliar novo em `JobCase`, `written(path, limit=30.0) -> int`, espera
o arquivo existir **com tamanho maior que zero** e devolve esse tamanho, ou zero se o teto de tempo
passar. No caso, a falha injetada agora só ocorre depois de `spawned.txt` e depois do primeiro
`beat.txt` com bytes; o tamanho observado é guardado e conferido logo após `supervise` retornar, com
mensagem clara (`"the unit never wrote a beat before the injected failure"`) se o beat nunca veio, e
com `assertEqual(len(beating), 1, ...)` provando que o status `running` foi de fato recusado uma vez.
Nenhuma asserção foi afrouxada: permanecem `state == "crashed"`, `effects == "uncertain"`,
`"no space left"` e `"failed internally"` em `detail`, a liveness `gone`/`unknown`, o
`assertEqual(beat.stat().st_size, first)` depois de 2 s de espera e o `wait` em `EXIT_INDETERMINATE`.
A espera bloqueia dentro do gancho antes de `containment.watch`, então não consome o prazo da
unidade.

Sonda discriminante. Numa cópia fora do repositório, `GRANDCHILD` foi alterado para dormir 3 s antes
de criar `beat.txt`, reproduzindo em ordem determinística exatamente a carga observada. Com o
arranjo desta rodada o caso passa (`Ran 1 test in 5.538s / OK`); com `written` neutralizado, isto é,
com o arranjo da rodada 16, o mesmo cenário reproduz o erro literal do portão:

```
    first = beat.stat().st_size
FileNotFoundError: [WinError 2] ...\tl-job-test-v2r6v74g\work\beat.txt
Ran 1 test in 0.388s
FAILED (errors=1)
```

Outros casos com a mesma pré-condição. Foram conferidos os três outros pontos da suíte que leem um
arquivo de batida: nenhum tem a pré-condição idêntica (unidade morta antes do primeiro beat), e por
isso nenhum foi alterado.

- `ContainmentTest.test_descendant_stops_working_when_the_unit_times_out` derruba a árvore por
  `--timeout 4`, ou seja, o descendente tem quatro segundos de vida antes da varredura, contra
  ~zero do caso corrigido. A morte ali é relógio do supervisor e o teste não tem como segurá-la, de
  modo que esperar pelo beat não tornaria o arranjo determinístico; a margem de quatro segundos
  contra dois arranques de Python é o que o sustenta. Ele passou nas duas execuções completas.
- `UnprovenSweepTest.test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered` é
  POSIX-only e o descendente ali sobrevive de propósito por 30 s; ele já espera o arquivo aparecer e
  a única janela restante é a de microssegundos entre criar e gravar, que produziria a mensagem clara
  do `assertGreater(first, 0, ...)` e não um erro opaco.
- `ForgedTerminalRecordTest` lê o beat por `beats()`, que já trata a ausência devolvendo zero.

Os três portões, nesta árvore, em Windows, offline. Primeiro a classe dirigida sozinha, cinco vezes
seguidas:

```
python -m unittest tests.test_tl_job.SupervisorFailureTest
Ran 3 tests in 3.137s / OK
Ran 3 tests in 3.148s / OK
Ran 3 tests in 3.150s / OK
Ran 3 tests in 3.137s / OK
Ran 3 tests in 3.135s / OK
(saída 0 nas cinco)
```

Depois a suíte completa, uma única passagem:

```
python -m unittest discover -s tests -p "test_*.py"
Ran 104 tests in 351.474s

OK (skipped=2)
(saída 0)
```

A contagem não mudou: continuam 104 casos em 23 classes, com os mesmos dois pulos já justificados no
fechamento acima. Nenhum caso foi criado, removido ou renomeado — a mudança é de arranjo dentro de um
caso existente, mais um auxiliar em `JobCase`.

```
python scripts/validate_repository.py
ERROR: invalid JSON .tl-work\claude8-reconcile-cmd.json: Expecting value: line 1 column 1 (char 0)
(saída 1)
```

Este portão falha por um arquivo que não pertence ao repositório. `.tl-work/` é o diretório de
rascunho do próprio host orquestrador, excluído por `.git/info/exclude:8:/.tl-work/` — não está sob
controle de versão, não está no manifesto e não é exportado. O arquivo acusado,
`claude8-reconcile-cmd.json`, foi escrito pelo host em 21:35 desta data e contém o texto de uso de
`tl_session.py reconcile`, não JSON. `validate_json()` (`scripts/validate_repository.py:68`) varre
`ROOT.rglob("*.json")` pulando apenas `.git` e `_tl-orc`, então enxerga o rascunho do host. Este papel
não apagou nem moveu o arquivo do host e não alterou o validador: o escopo desta rodada é a corrida no
arranjo do teste. Como `fail()` interrompe na primeira ocorrência, o restante do validador ficaria sem
execução; uma sonda fora do repositório repetiu `main()` com a varredura de JSON pulando também
`.tl-work`, e o conteúdo do repositório valida:

```
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
(saída 0)
```

```
git diff --check
(sem saída, saída 0)
```

O limite de `git diff --check` é o mesmo do fechamento acima: `tests/` continua `??` em
`git status --porcelain`. `git diff --check --no-index /dev/null tests/test_tl_job.py` também não
apontou nada (a saída 1 ali é a diferença entre os arquivos, não um achado de espaço em branco).

## Adendo — registro terminal malformado e claim que não pode ser inspecionado (rodada 18, 2026-09-11)

Nota de numeração: a rodada 17 corrigiu só a corrida no arranjo do teste e ficou registrada como
subseção do adendo da rodada 16 acima, por isso não há adendo próprio com aquele número.

Escopo congelado desta rodada: dois achados, nada além deles. Nenhuma tarefa T001–T011 foi tocada,
nenhum serviço, dependência ou credencial foi criado, e nenhum commit foi feito.

### O que mudou

**[R1] Um registro terminal sem contenção era lido como entrega.** `containment` não estava em
`REQUIRED_RESULT_KEYS` e `admitted_logs` aceitava um mapa de logs vazio ou pela metade. Apagar
`containment` de um resultado normal fazia `swept_proven(None)` responder verdadeiro, e o leitor
publicava `effects: known` com saída 0 — entregando uma unidade cuja árvore nunca foi prestada
contas. Em `scripts/tl_job.py`:

- `REQUIRED_RESULT_KEYS` passa a exigir `containment`;
- `CONTAINMENT_KEYS` ganha tipo por campo, `CONTAINMENT_REQUIRED = ("kind", "established",
  "unit_ran")` e `LOG_NAMES = frozenset({"stdout", "stderr"})`;
- `admitted_containment` só reconstrói registro completo, tipado e coerente na própria forma
  (estabelecido exige `swept`; não estabelecido não pode varrer árvore que não criou);
- `admitted_logs` exige exatamente o par, não um subconjunto dele;
- `swept_proven` trata não-dicionário como não provado;
- do lado escritor, `Containment.describe` passa a escrever `unit_ran`, o ramo de `Popen` recusado
  em `run_under_containment` grava o registro que descreve a recusa, e `finalize` garante um
  registro em todo caminho terminal. Sem isso o leitor mais estrito recusaria finais legítimos.

**[R2] Falha de `stat` no manifesto era tratada como manifesto ausente.** `read_claim_file`
capturava `OSError` genérico de `path.stat()` e devolvia `absent`; `load_claim` então gastava a
janela de claim e respondia `conflict` — outro processo segurando a unidade — para um diretório de
estado que este supervisor simplesmente não consegue ler. Agora `FileNotFoundError` continua sendo
`absent` (é o rename em voo, a única coisa que resolve sozinha) e qualquer outro `OSError` devolve
`it cannot be inspected: <motivo>`, que `refuse_manifest` transforma em `EXIT_USAGE` /
`invalid_input` / `effects: none`, sem espera.

### Casos novos em `tests/test_tl_job.py`

Sete casos, nenhuma classe nova. Em `ReportAllowlistTest`: registro terminal válido com
`containment` removido; registro com contenção parcial (quatro formas, por `subTest`); registro com
`logs` vazio e com metade do par (três formas); e a discriminação, que confere que o registro
realmente escrito pelo supervisor carrega os três campos e continua entregue com saída 0. Em
`MalformedClaimTest`: `Path.stat` remendado para negar permissão só em `manifest.json` — um caso no
nível do auxiliar (`read_claim_file` não responde `absent`), um ponta a ponta (`invalid_input` sem
consumir a janela) e a discriminação de que um nome que de fato não existe continua sendo `absent`.

Um arranjo pré-existente precisou acompanhar a regra: `UnprovableTerminationTest.forge()` monta "o
registro que a própria unidade conseguiria montar", e completo agora inclui contenção. O registro
forjado passou a trazer a contenção mais forte possível (árvore estabelecida e varrida por escopo
provado), que é exatamente o ponto da classe: nem assim há entrega sem a prova do lease. Nenhuma
asserção foi afrouxada.

### Portões, na ordem em que rodaram

Dirigidos primeiro, só as duas classes tocadas:

```
python -m unittest tests.test_tl_job.ReportAllowlistTest tests.test_tl_job.MalformedClaimTest -v
Ran 20 tests in 13.926s
OK
(saída 0)
```

Depois da correção do arranjo em `forge()`:

```
python -m unittest tests.test_tl_job.UnprovableTerminationTest -v
Ran 4 tests in 0.244s
OK
(saída 0)
```

Sondas discriminantes, em cópias isoladas fora do repositório (no diretório de rascunho da sessão,
com `scripts/` e `tests/` copiados). **[R1]**, com a exigência nova desfeita — `containment` fora de
`REQUIRED_RESULT_KEYS`, reconstrução condicional, `swept_proven` voltando a ler ausência como prova
e `admitted_logs` aceitando subconjunto:

```
python -m unittest tests.test_tl_job.ReportAllowlistTest
Ran 10 tests in 9.617s
FAILED (failures=4)
AssertionError: 0 != 5 : {... 'effects': 'known', 'exit_code': 0, 'outcome': 'delivered',
                          'result_status': 'admitted', 'state': 'exited', ...}
```

Isto é o achado reproduzido literalmente: sem a exigência, o registro sem contenção volta a ser
entregue com saída 0 e efeitos conhecidos. As outras três falhas são os três formatos de `logs`
incompletos.

**[R2]**, com o mapeamento antigo restaurado (`except OSError: return "absent", None`):

```
python -m unittest tests.test_tl_job.MalformedClaimTest
Ran 10 tests in 8.887s
FAILED (failures=2)
AssertionError: 3 != 2 : {'effects': 'uncertain', 'error': 'an incomplete claim already holds this
  unit; inspect the state directory by hand', 'state': 'conflict', ...}
AssertionError: 'absent' == 'absent'
```

Também literal: saída 3, `conflict`, para um claim que só não pôde ser inspecionado.

Limite honesto das duas sondas: `scripts/tl_job.py` e `tests/` são arquivos não rastreados (`??`),
então não há versão anterior recuperável por `git`, e o histórico da sessão anterior não está
acessível a partir desta. As cópias isoladas, portanto, desfazem exatamente as defesas que esta
rodada acrescentou — não são uma restauração byte a byte de um original. O que elas provam é a
discriminação pedida: removida a defesa nova, o caso volta a entregar; com ela, não.

Suíte completa, uma única passagem na revisão final:

```
python -m unittest discover -s tests -p "test_*.py"
Ran 111 tests in 357.954s
OK (skipped=2)
(saída 0)
```

São 104 casos anteriores mais os sete desta rodada, nas mesmas 23 classes; os dois pulos são os já
justificados (POSIX-only e ausência de lock exclusivo).

Depois dessa passagem, esta rodada ainda editou registro e documentação — esta evidência, a Task,
`docs/EXECUTION_PROTOCOL.md` e `CHANGELOG.md` —, e nenhuma dessas edições toca código ou é lida por
teste algum (`grep` por `EXECUTION_PROTOCOL` e `CHANGELOG` em `tests/` não devolve nada). Ainda
assim, para que a revisão final inteira tenha uma passagem verde, a suíte foi rodada de novo com os
documentos já no estado final:

```
python -m unittest discover -s tests -p "test_*.py"
Ran 111 tests in 359.613s
OK (skipped=2)
(saída 0)
```

Os dois portões estruturais foram repetidos no mesmo estado final: `python
scripts/validate_repository.py` → `OK: 19 package files; …`, saída `0`; `git diff --check` → sem
saída, saída `0`.

```
python scripts/validate_repository.py
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
(saída 0)
```

```
git diff --check
(sem saída, saída 0)
```

O limite deste portão é o de sempre e vale de novo: `git diff --check` só enxerga arquivo rastreado,
e `scripts/tl_job.py` e `tests/` continuam `??`. Os dois foram conferidos por leitura direta dos
bytes: fim de linha LF, zero linhas com espaço em branco terminal, zero tabulações. Nenhuma linha
nova ultrapassa 110 colunas (as que ultrapassam em `scripts/tl_job.py` e `tests/test_tl_job.py` são
pré-existentes e fora das regiões editadas).

O que estes portões não provam: nenhuma medição de economia de tokens foi feita nesta rodada, e
nenhuma é reivindicada. O comportamento sob negação real de permissão de sistema de arquivos foi
exercitado por remendo em `Path.stat`, não por uma ACL de verdade.

## Adendo — descendente que escapa do grupo, inspeção do `result_file` e teto de bytes dentro da fronteira (rodada 19, 2026-09-12)

Origem: parecer do Checker `e27d4767` (Codex, `gpt-5.6-terra`, high) com três achados: R1 (alta)
um descendente POSIX que chama `setsid()` sobrevive à varredura do grupo e, depois que o supervisor
solta a lease, pode reescrever `result.json` com um registro terminal forjado; R2 (média) a
inspeção do `result_file` antes do spawn tratava qualquer `OSError` como ausência, então um caminho
que não pode ser inspecionado era lido como "livre" e o comando rodava; R3 (média) um `--max-bytes`
inválido era recusado pelo `argparse`, saindo pela mensagem de uso, que não é JSON nem limitada.

Como a rodada correu, sem omissão: a sessão Maker `7a5cf172` (Claude, `claude-opus-5`, high)
começou às 00:54 e foi cortada pelo executor às 01:54 no teto privado `max_call_seconds` (3600 s),
sem recibo. O reconcile `effect_inspected` atribuiu o efeito ao run (digest `e2f70117…`, igual ao
snapshot conferido pelo host). As edições estavam completas na árvore; o host verificou, registrou
este adendo e o atribuiu com `evidence --author-family anthropic`, e retomou apenas gates, Checker
e prova, sem nova sessão Maker. A sessão anterior morta às 23:23 (edições parciais) foi absorvida
por esta: nada dela ficou sem teste.

Escopo congelado desta rodada: os três achados, nada além deles. Nenhuma tarefa T001–T011 foi
tocada, nenhum serviço, dependência ou credencial foi criado, e nenhum commit foi feito.

### O que mudou

- **R1.** O registro terminal passa a carregar `containment.scope` e `containment.failure`.
  `PROVEN_SCOPES` (`job_object`, `process_group`) prova que a árvore varrida terminou;
  `ACCOUNTED_SCOPES` (`job_object`, `subreaper_scan`) prova que descendentes que **saíram** do
  grupo foram contabilizados. Um registro sem escopo contabilizado é lido como indeterminado por
  `wait`, `status` e `result`, por mais completo e terminal que pareça, e nunca vira `delivered`.
  No Windows, `JobObjectContainment` (Job Object com kill-on-close) contém a árvore inteira,
  inclusive processos que se desligam do grupo. No Linux, `become_subreaper()`
  (`PR_SET_CHILD_SUBREAPER`) reparenta os fugitivos ao supervisor para que a varredura os alcance;
  em outros POSIX o escopo fica `unaccounted` e o resultado é indeterminado, declarado assim.
- **R2.** A inspeção do `result_file` antes do spawn usa `os.lstat` e só `FileNotFoundError` prova
  ausência. Qualquer outro `OSError` (permissão negada, diretório inacessível) recusa a unidade com
  `invalid_input` **antes** de qualquer comando rodar, em vez de supor caminho limpo.
- **R3.** `check_max_bytes` valida o teto dentro da fronteira `JobError` do `main`: valor não
  numérico vira recibo JSON limitado (`invalid_input`, saída de uso), com o teto padrão limitando a
  própria recusa; valor abaixo do piso é grampeado como nos demais chamadores de `emit`.

### Casos novos em `tests/test_tl_job.py`

- `EscapedDescendantTest` (4): descendente `setsid` não forja resultado depois da lease (só Linux,
  pulado no Windows); descendente desligado não escapa do Job Object (só Windows); o registro
  forjado seria entregue se algum dia pousasse (prova de que o teste morde); contenção base não
  responde por nada e o Job Object responde por tudo.
- `SweepFailureTest` (+2): Job Object que recusa terminar não é reportado como contido; só o que
  termina é.
- `ForgedTerminalResultTest` (+1): nem `wait` nem `result` entregam enquanto a unidade forjadora
  continua escrevendo.
- `UninspectableResultTest` (3): o helper distingue inspeção negada de ausência real; caminho que
  não pode ser inspecionado não roda comando algum; o mesmo arranjo roda quando o caminho é
  inspecionável.
- `MalformedClaimTest` (+2): claim que não pode ser inspecionado não é reportado como ausente e
  vira `invalid_input` sem esperar.
- `MalformedCeilingTest` (2): teto não numérico é recusa JSON limitada, não despejo de uso, e
  recusa antes de qualquer comando rodar.

### Portões, na ordem em que rodaram (host, Windows)

Dirigidos primeiro, só as classes tocadas mais as de plataforma:

```
python -m unittest tests.test_tl_job.EscapedDescendantTest tests.test_tl_job.UninspectableResultTest tests.test_tl_job.MalformedCeilingTest tests.test_tl_job.SweepFailureTest tests.test_tl_job.MalformedClaimTest tests.test_tl_job.UnprovenSweepTest tests.test_tl_job.InputTest tests.test_tl_job.SupervisorBoundaryTest -v
Ran 56 tests in 209.248s
OK (skipped=3)
(saída 0)
```

Suíte completa:

```
python -m unittest discover -s tests -p "test_*.py"
Ran 124 tests in 365.987s
OK (skipped=3)
(saída 0)
```

Os três pulados, nomeados: `EscapedDescendantTest.test_a_setsid_descendant_cannot_forge_a_delivered_result_after_the_lease`
(só Linux), `UnprovenSweepTest.test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered`
(só POSIX) e `InputTest.test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused` (esta
sessão Windows não pode criar o link). O ramo Linux de R1 (`subreaper_scan`) só é exercitado pelo
CI; localmente ele não foi executado.

```
python scripts/validate_repository.py   (saída 0)
git diff --check                        (saída 0)
```

Depois destes portões do host, o executor rerodou os portões `validate-repository`, `job-tests` e
`diff-check` e despachou o Checker; o parecer fica registrado no estado do run, não aqui.

## Adendo — prova de fim ligada ao arquivo do lease, não ao nome (rodada 20, 2026-09-12)

Origem: parecer do Checker desta rodada com um único achado, R1: o caminho do lease não estava
ligado ao inode da trava que o supervisor segura, então uma unidade podia substituir
`supervisor.lock` com o supervisor ainda vivo, fazendo a liveness responder `gone` e o término
responder `proven`. A correção pedida: usar testemunha de término inforjável, de posse do
supervisor, ou impedir/recusar a substituição do caminho do lease, e acrescentar um teste negativo
ponta a ponta em que uma unidade viva troca `supervisor.lock`, forja registro terminal completo e
continua escrevendo — `wait` e `result` têm de seguir não entregando.

Escopo congelado desta rodada: esse único achado, nada além dele. Nenhuma tarefa T001–T011 foi
tocada, nenhum outro achado foi respondido, nenhum serviço, dependência ou credencial foi criado,
nenhum teste existente foi afrouxado e nenhum commit foi feito por este papel.

O defeito, na forma em que existia: `claim_lease` abria `supervisor.lock` pelo nome e perguntava
apenas se aquele arquivo estava travado. A unidade tem acesso de escrita ao próprio diretório de
job, então `os.replace(outro_arquivo, "supervisor.lock")` punha ali um arquivo sem trava alguma com
o supervisor ainda vivo: `supervisor_liveness` respondia `gone`, `termination_proof` respondia
`proven`, e um `result.json` forjado pela própria unidade era publicado como `outcome: delivered`,
`effects: known`, saída `0`. A trava provava um arquivo; o leitor perguntava por um nome.

### O que mudou

- **Reivindicação ligada ao inode.** `command_start` cria o arquivo do lease **antes** de escrever
  o manifesto (`create_lease`, que abre em `a+b` e devolve `f"{st_dev}:{st_ino}"` do descritor) e
  grava o par em `manifest.json` como `lease_identity`. O campo entra no esquema do manifesto e é
  validado como qualquer outro: `usable_identity` aceita `unbound` ou `dispositivo:inode` com
  dígitos, até `LEASE_IDENTITY_MAX` (80) caracteres, e um valor corrompido é recusado como
  manifesto inválido (`invalid_input`, `effects: none`, saída `2`) por todos os leitores.
- **A comparação é sobre o descritor aberto, não sobre o caminho.** `lease_verdict(handle, expected)`
  compara `lease_identity(os.fstat(handle.fileno()))` com o valor reivindicado e devolve `same`,
  `other` ou `unbound`. Nada é decidido por `os.stat` do nome, que é justamente o que o atacante
  controla.
- **Veredito quando o nome leva a outro arquivo.** `claim_lease` devolve `Lease(None, "replaced",
  "the lease path no longer names the file this claim recorded")`; `supervisor_liveness` responde
  `replaced` e `termination_proof` responde `replaced`, que entra em `UNPROVABLE_END` com frase
  própria. `wait` e `result` recusam com `indeterminate`, `effects: uncertain`, saída `5` e o campo
  `termination` nomeando o fim que não pôde ser provado; nenhum recibo carrega `outcome`.
- **O supervisor não começa sobre diretório adulterado.** `supervise` reivindica o lease com a
  identidade do manifesto e, em `replaced`, levanta `conflict` com `effects: none` e saída `3` —
  "the lease path of this unit no longer names the file its claim recorded; this job directory was
  tampered with and is not run again" —, sem executar argv.
- **Reivindicação sem identidade útil nunca prova fim.** `lease_identity` devolve `unbound` quando
  o `st_ino` é 0 (plataforma que não identifica arquivo), e um claim `unbound` — inclusive os da
  forma anterior — lê liveness `unbound` e prova `unproven`. Fecha fechado, nos dois sentidos.
- **A identidade do claim não muda.** `manifest_fingerprint` continua sobre
  `("unit", "authorization_fingerprint", "cwd", "argv", "timeout", "result_file")`, então
  `lease_identity` não desloca o reaproveitamento idempotente do `start`.
- **Registro.** `docs/EXECUTION_PROTOCOL.md` ganhou o mecanismo (na seção do lease, com os
  vereditos, os códigos e a independência da impressão digital) e o limite honesto (em `## Limites`);
  `CHANGELOG.md` ganhou o item correspondente em `### Alterado` de `## [0.8.0] - 2026-09-11`.

### Casos novos em `tests/test_tl_job.py`

Dez casos, em duas classes novas. A árvore atual passa a ter 134 casos em 28 classes; contagens
menores citadas em adendos anteriores descrevem aquelas rodadas e não esta.

- `ReplacedLeaseTest` (2): o negativo ponta a ponta pedido pelo achado — unidade viva troca
  `supervisor.lock` por um arquivo sem trava, escreve `result.json` terminal completo (contenção
  cheia, par de logs, `outcome: delivered`) e continua escrevendo; `wait` e `result` respondem
  `indeterminate`, `effects: uncertain`, saída `5`, `termination` `replaced`, sem `outcome` — e o
  segundo caso mostra que nem depois de a unidade terminar de verdade aquele diretório volta a
  provar fim.
- `LeaseBindingTest` (8): `start` grava a identidade do arquivo que ele mesmo criou; a identidade
  não participa da impressão digital (dois `start` da mesma linha autorizada continuam sendo o
  mesmo claim); `lease_identity` corrompido é recusado como manifesto inválido; lease trocado e
  lease `unbound` respondem `replaced`/`unbound` na liveness e nunca `proven` na prova;
  `claim_lease` recusa o nome que passou a levar a outro arquivo; `supervise` recusa o diretório
  adulterado com `conflict` e saída `3`; e os dois leitores sobre lease trocado são verificados
  campo a campo.

Comportamento por plataforma, declarado: em POSIX o `os.replace` sobre o lease segurado é permitido
e é a ligação por inode que recusa o ataque; no Windows o próprio sistema recusa trocar ou remover o
arquivo sob descritor aberto (`PermissionError`, errno 13) e o supervisor segue `alive`. Os testes
aceitam os dois caminhos porque a resposta a quem pergunta é a mesma nos dois: não-entrega. Isso é
limite, não detecção — está dito assim em `## Limites` do protocolo.

### Portões, na ordem em que rodaram (host, Windows, offline)

Dirigidos primeiro, só as duas classes novas:

```
python -m unittest tests.test_tl_job.ReplacedLeaseTest tests.test_tl_job.LeaseBindingTest -v
Ran 10 tests in 10.349s
OK
(saída 0)
```

Suíte completa da revisão final:

```
python -m unittest discover -s tests -p "test_*.py"
Ran 134 tests in 384.895s
OK (skipped=3)
(saída 0)
```

Os três pulados são os mesmos já nomeados no adendo da rodada 19:
`EscapedDescendantTest.test_a_setsid_descendant_cannot_forge_a_delivered_result_after_the_lease`
(só Linux), `UnprovenSweepTest.test_a_unit_whose_tree_was_never_proven_ended_is_not_reported_as_delivered`
(só POSIX) e `InputTest.test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused` (esta
sessão Windows não pode criar o link). Nenhum caso novo desta rodada foi pulado.

```
python scripts/validate_repository.py
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
(saída 0)

git diff --check                        (sem saída, saída 0)
```

`git diff --check` só enxerga arquivo rastreado; `scripts/tl_job.py` e `tests/` continuam `??` e
foram conferidos por leitura direta — LF puro, zero espaço em branco terminal, zero tabulação.

### Falha observada e não corrigida, por estar fora do escopo congelado

**Superada na rodada 21**, cujo adendo está no fim deste arquivo: o achado abaixo virou o
escopo congelado da rodada seguinte e foi corrigido lá. O relato permanece como está, sem
reescrita, porque é o registro do que esta rodada viu e decidiu não tocar.

A primeira passagem completa desta revisão saiu `Ran 134 tests in 384.653s`, `FAILED (failures=1,
skipped=3)`, em `ClaimValidationTest.test_concurrent_starts_on_the_same_unit_leave_one_claim_and_one_receipt`:
um dos três `start` simultâneos saiu `2` com
`the claim for this unit is not a usable manifest: it could not be read: Permission denied`, onde se
esperava `[0, 0, 0]`. Isolado logo em seguida, o mesmo caso passou seis vezes seguidas
(`python -m unittest tests.test_tl_job.ClaimValidationTest.test_concurrent_starts_on_the_same_unit_leave_one_claim_and_one_receipt`,
`OK` em 6/6), e a passagem completa seguinte, sem nenhuma alteração de código entre as duas, saiu
`OK (skipped=3)`.

O que é, dito sem suavizar: uma corrida real, não um defeito do teste. No Windows, o `os.replace`
que publica `manifest.json` deixa o nome antigo em exclusão pendente por um instante, e um leitor
que abra exatamente nessa janela recebe `PermissionError` (errno 13). `read_claim_file` classifica
qualquer `OSError` de leitura como claim presente e inutilizável — decisão deliberada das rodadas 16
e 18, tomada contra o oposto (esperar por algo que não se resolve) —, então um transitório de
milissegundos vira `invalid_input` num `start` concorrente legítimo. O código dessa classificação e
o teste são anteriores a esta rodada; a mudança de R1 apenas insere a criação do arquivo do lease
antes da escrita do manifesto, o que não altera a largura da janela do `os.replace`.

Não foi corrigido aqui porque corrigir exigiria mexer na semântica de `read_claim_file`, que está
fora do único achado congelado desta rodada, e porque a correção óbvia (reclassificar o transitório
como espera) é exatamente o que a rodada 18 removeu de propósito. Fica apontado para o condutor como
achado próprio, com a reprodução acima: é uma falha rara e dependente de plataforma, e um `start`
concorrente pode, sob ela, receber `invalid_input` no lugar de reaproveitar o claim.

## Adendo — reivindicação que está pousando não é reivindicação quebrada (rodada 21, 2026-09-12)

Origem: parecer do Checker desta rodada com um único achado, R1: um `start` concorrente legítimo
podia ser recusado como `invalid_input` durante a publicação atômica do manifesto no Windows. A
correção pedida: tratar o erro transitório de compartilhamento documentado como repetição limitada
apenas enquanto a janela de publicação da reivindicação está aberta, preservando a recusa imediata
para reivindicação estável ilegível; acrescentar uma sonda negativa determinística, em cópia
isolada, que force esse transitório e prove que `start` concorrentes reaproveitam uma reivindicação
e uma execução em vez de responder `invalid_input`; e manter um teste separado provando que falha
permanente de inspeção continua falhando de imediato.

Escopo congelado desta rodada: esse único achado, nada além dele. Nenhuma tarefa T001–T011 foi
tocada, nenhum outro achado foi respondido, nenhum serviço, dependência ou credencial foi criado,
nenhum teste existente foi afrouxado e nenhum commit foi feito por este papel. O achado é
exatamente o que a rodada 20 registrou acima como próprio e fora de escopo; agora está dentro.

O defeito, na forma em que existia: `read_claim_file` classificava **qualquer** `OSError` da leitura
do manifesto como reivindicação presente e inutilizável, e `load_claim` recusava sem espera. No
Windows, o nome que `os.replace` acabou de criar pode recusar uma abertura por um instante — o
`PermissionError` que a rodada 20 viu na suíte completa. Resultado: o perdedor de uma corrida que
deveria reaproveitar a reivindicação do vencedor saía `invalid_input`, `effects: none`, saída `2`.
A distinção que faltava não é entre erros, é entre um nome que está mudando e um nome que está
quebrado.

### O que mudou

- **Uma classe nova de resposta do leitor, e só uma.** `publication_denial(exc)` responde verdadeiro
  para `winerror` 5 (acesso negado), 32 (violação de compartilhamento) e 33 (violação de bloqueio)
  e, sem `winerror`, para `EACCES`/`EPERM`. `read_claim_file` só marca o motivo com o prefixo
  `CLAIM_PUBLISHING` quando a **abertura** é recusada — a inspeção (`stat`) daquele mesmo nome já
  tinha passado, que é o que torna a hipótese "publicação em voo" estreita em vez de genérica.
- **Orçamento fixo, aberto uma vez.** `load_claim` abre `CLAIM_PUBLISH_SECONDS` (1,0 s) na primeira
  negativa marcada e nunca o reinicia: negativa nova dentro da mesma chamada não compra tempo novo.
  Passado o orçamento, volta a mesma recusa de sempre — `invalid_input`, `effects: none`, saída `2`
  — com o motivo original e sem a marca, que é interna e nunca chega a um recibo.
- **O que não mudou, de propósito.** Reivindicação estável ilegível (JSON inválido, não UTF-8, acima
  do teto, não objeto) segue recusada na primeira leitura; nome que sequer pode ser inspecionado
  (`stat` negado) segue recusado de imediato, sem orçamento; erro de leitura que não é negativa
  (`EIO`) segue recusado na primeira tentativa; e `absent` continua com a janela de
  `CLAIM_WAIT_SECONDS` terminando em `conflict`. Nada é reparado: a repetição só relê, e o teste
  compara os bytes do manifesto antes e depois.
- **Registro.** `docs/EXECUTION_PROTOCOL.md` ganhou o parágrafo do caso estreito entre manifesto
  ausente e manifesto ilegível, com o orçamento, a recusa idêntica passado ele e o limite de
  plataforma; `CHANGELOG.md` ganhou o item correspondente em `### Alterado` de
  `## [0.8.0] - 2026-09-11`.

### Casos novos em `tests/test_tl_job.py`

Oito casos, em uma classe nova, `ClaimPublicationWindowTest`. A árvore atual passa a ter 142 casos
em 29 classes; contagens menores citadas em adendos anteriores descrevem aquelas rodadas e não esta.
A janela é **forçada**, não disputada: `Path.read_text` é remendado para negar apenas
`manifest.json` e apenas um número declarado de vezes, então a prova é determinística e não depende
de ganhar uma corrida de milissegundos.

- A sonda negativa pedida: um `start` real publica a reivindicação, um segundo `start` da mesma
  identidade atravessa três negativas forçadas e sai `EXIT_OK` com `reused`, nunca `invalid_input`,
  dentro de `CLAIM_WAIT_SECONDS`; os bytes do manifesto são idênticos antes e depois; `wait`
  entrega e a unidade deixa `effect.log` com uma linha só.
- Três `start` da mesma identidade atravessando a janela: um diretório de job, uma execução.
- Negativa que nunca passa: recusada como reivindicação inutilizável (`invalid_input`,
  `effects: none`, saída `2`), com mais de uma tentativa, depois do orçamento e antes da janela de
  ausência, sem marca no texto do erro, sem `status.json`, `result.json`, `supervisor.json` ou
  lease, e sem a unidade ter rodado.
- Orçamento aberto uma vez: leituras alternando negativa e ausência para sempre terminam em
  `invalid_input` dentro de `CLAIM_WAIT_SECONDS`, nunca em `conflict`.
- Inspeção negada (`Path.stat`) continua recusada de imediato, em menos que o próprio orçamento —
  este é o teste de recusa que o achado pediu que fosse mantido.
- Erro de leitura que não é negativa (`EIO`) recusado após exatamente uma tentativa.
- Tabela do predicado: 5/32/33 verdadeiros; 2, 3 e 1224 falsos; `EACCES`/`EPERM` sem `winerror`
  verdadeiros; `EIO`, `EISDIR`, `ENOENT`, `ENAMETOOLONG` falsos.
- A marca interna nunca vaza: `read_claim_file` segue respondendo `claim` e
  `it is not valid JSON` sem prefixo algum.

### Prova por discriminação, em cópia isolada fora do repositório

Cópia de `scripts/tl_job.py` e `tests/test_tl_job.py` com uma única linha desfeita — a
classificação da negativa volta a `return detail, None` — e a mesma classe rodada nos dois lados:

```
python -m unittest tests.test_tl_job.ClaimPublicationWindowTest      (cópia pré-correção)
FAIL: test_a_start_inside_the_publication_window_reuses_the_claim_instead_of_refusing
AssertionError: 'invalid_input' == 'invalid_input' : {'effects': 'none', 'error': 'the claim for
this unit is not a usable manifest: it could not be read: Permission denied', 'job_id': 'T012',
'schema': 1, 'state': 'invalid_input', 'unit': 'T012'}
FAIL: test_three_starts_of_one_identity_through_the_window_run_the_unit_once
AssertionError: 1 != 2
FAIL: test_a_denial_that_never_clears_is_refused_as_an_unusable_claim
AssertionError: 1 not greater than 1 : the denial was refused without the budget it is owed
Ran 8 tests in 1.828s
FAILED (failures=3)
(saída 1)

python -m unittest tests.test_tl_job.ClaimPublicationWindowTest      (árvore corrigida)
Ran 8 tests in 2.516s
OK
(saída 0)
```

Limite declarado, o mesmo das rodadas anteriores: como os dois arquivos não são rastreados, a cópia
desfaz exatamente a defesa desta rodada, não restaura um original recuperado por `git`.

### A corrida real, repetida

O caso que falhou uma vez na rodada 20 é comportamental e não forçado; rodado quinze vezes seguidas
sobre a árvore corrigida, em processos separados:

```
python -m unittest tests.test_tl_job.ClaimValidationTest.test_concurrent_starts_on_the_same_unit_leave_one_claim_and_one_receipt
(15 execuções consecutivas, cada uma OK; failures: 0/15)
```

Isto é repetição, não prova de ausência: uma corrida que não reaparece em quinze tentativas continua
sendo uma corrida. A prova de que a janela é tratada está na sonda determinística acima, não aqui.

### Portões, na ordem em que rodaram (host, Windows, offline)

Dirigidos primeiro, a classe nova e as duas classes vizinhas que compartilham a semântica do leitor:

```
python -m unittest tests.test_tl_job.ClaimPublicationWindowTest tests.test_tl_job.MalformedClaimTest tests.test_tl_job.ClaimValidationTest
Ran 24 tests in 9.598s
OK
(saída 0)
```

Suíte completa da revisão final:

```
python -m unittest discover -s tests -p "test_*.py"
Ran 142 tests in 389.131s
OK (skipped=3)
(saída 0)
```

Os três pulados são os mesmos das rodadas anteriores, por plataforma (link e permissão POSIX).
Nenhum caso novo desta rodada foi pulado.

```
python scripts/validate_repository.py
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
(saída 0)

git diff --check                        (sem saída, saída 0)
```

`git diff --check` só enxerga arquivo rastreado; `scripts/tl_job.py` e `tests/` continuam `??` e
foram conferidos por leitura direta — LF puro, zero espaço em branco terminal, zero tabulação.

### Limite honesto desta rodada

Em POSIX a classe de erro tratada é, na prática, vazia: abrir um arquivo recém-renomeado não é
recusado, então o orçamento nunca chega a ser aberto num host Linux ou macOS. O predicado mesmo
assim aceita `EACCES`/`EPERM` sem `winerror`, e essa foi uma escolha: um desvio por plataforma
seria código que os testes não conseguiriam exercitar dos dois lados. O preço é declarado — num
host POSIX onde a leitura do manifesto é negada por permissão de verdade, a recusa chega um segundo
depois, e não de imediato, com a mesma resposta e o mesmo código de saída. O orçamento é fixo em
código, não configurável, e não há retentativa alguma na escrita: `manifest.json` continua sendo
publicado exatamente uma vez, por um único `os.replace`.

## Adendo — a vinculação esperada mora fora do que a unidade escreve (rodada 22, 2026-09-12)

Origem: parecer do Checker desta rodada com um único achado, R1: uma unidade podia contornar a
proteção da rodada 20 substituindo o `supervisor.lock` **e** reescrevendo o `manifest.json` com o
`lease_identity` do arquivo plantado; os leitores passavam a confiar na reivindicação reescrita e
podiam entregar um resultado terminal forjado com o supervisor original ainda vivo. A correção
pedida: ancorar a vinculação esperada entre lease e reivindicação fora dos artefatos mutáveis do
job, exigir que `wait` e `result` a validem antes de entregar, e recusar fechado quando ela não
responder; mais um teste negativo ponta a ponta determinístico, em cópia isolada, onde uma unidade
viva substitui o `supervisor.lock`, reescreve o `lease_identity` do `manifest.json` para o arquivo
plantado, forja o `result.json` e continua escrevendo — `wait` e `result` devem permanecer sem
entregar.

Escopo congelado desta rodada: esse único achado, nada além dele. Nenhuma tarefa T001–T011 foi
tocada, nenhum outro achado foi respondido, nenhum serviço, dependência ou credencial foi criado,
nenhum teste existente foi afrouxado, nada saiu para a rede e nenhum commit foi feito por este papel.

O defeito, na forma em que existia: a rodada 20 ligou a prova ao arquivo do lease, mas guardou a
identidade esperada no `manifest.json` — que fica no diretório da unidade, onde a unidade escreve.
E `lease_identity` está deliberadamente fora de `manifest_fingerprint`, para que dois `start` da
mesma linha de comando ainda reaproveitem. Então trocar o lease e apontar a reivindicação para o
arquivo plantado recompunha a coerência: liveness `gone`, fim provado, registro forjado entregue
como sucesso. O que faltava não era outra comparação, era um lugar para guardar o que se compara.

### O que mudou

- **A vinculação é publicada fora do diretório da unidade, uma vez.** `start` escreve
  `<state-dir>/anchors/<unidade>.json` com `os.O_CREAT | os.O_EXCL` e modo `0o600`, **antes** da
  reivindicação. Ela guarda `schema`, `unit`, `lease_identity`, `manifest_fingerprint`,
  `authorization_fingerprint` e `binding`, um token curto derivado desses mesmos campos.
- **O token é recomputado, nunca acreditado.** `read_anchor` confere conjunto de chaves, tipos,
  schema, unidade e identidade utilizável, e só então compara `binding` com `binding_token(anchor)`:
  um registro que não responde pelos próprios campos não é uma vinculação, seja quem for que o
  escreveu.
- **`binding_check` responde três coisas.** `bound`, com a identidade a esperar; `diverged` quando a
  reivindicação no disco não é aquela para a qual a vinculação foi publicada — inclusive quando só o
  `lease_identity` foi reescrito, que é exatamente o achado; `unanchored` quando não há vinculação
  legível. Só `bound` carrega identidade.
- **Fechado por omissão.** `diverged` e `unanchored` entram em `SETTLED_UNPROVABLE` junto com
  `replaced`: `wait` para de esperar e responde na hora, `result` recusa, ambos `indeterminate`,
  `effects: uncertain`, saída `5`, com `termination` nomeando o que não pôde ser provado.
  `supervise` recusa com `conflict`, `effects: none`, saída `3`, sem executar argv algum. O
  reaproveitamento do `start` só é oferecido enquanto o estado for `bound`.
- **A vinculação existente jamais é sobrescrita.** `start` sobre unidade cuja vinculação já está lá,
  com o diretório de job apagado, recusa com `conflict` em vez de emitir vinculação nova.
- **Fora do disco.** O recibo de `start` devolve o token em `binding`, e `wait`/`result` aceitam
  `--expect-binding`: a forma (dezesseis hexadecimais minúsculos) é conferida **antes** de qualquer
  diretório ser procurado — fora dela, `invalid_input`, `effects: none`, saída `2` — e a origem antes
  de qualquer entrega — token bem formado de outra execução recusa como `diverged`.
- **Registro.** `docs/EXECUTION_PROTOCOL.md` ganhou os parágrafos da vinculação, o valor novo na
  lista de `termination` e o limite em **Limites**; `CHANGELOG.md` ganhou o item correspondente em
  `### Alterado` de `## [0.8.0] - 2026-09-11`.

### Casos novos em `tests/test_tl_job.py`

Doze casos: `BindingAnchorTest` (nove), `RewrittenClaimTest` (dois) e um caso residual em
`LeaseBindingTest`. A árvore atual passa a ter 154 casos em 31 classes; contagens menores citadas em
adendos anteriores descrevem aquelas rodadas e não esta.

- O negativo ponta a ponta pedido, `RewrittenClaimTest.test_a_unit_that_rewrites_its_claim_still_`
  `gets_no_delivery`: a unidade viva substitui o lease, aponta a reivindicação para o arquivo
  plantado, forja um `result.json` completo (`outcome: delivered`) e continua escrevendo. O teste lê
  do disco a premissa antes de concluir — a reivindicação nomeia o arquivo plantado, a vinculação
  não, e `manifest_fingerprint` continua idêntico, que é por que nada a jusante teria notado. `wait`
  e `result` respondem `indeterminate`, `termination: diverged`, saída `5`.
- O mesmo ataque deixando a unidade terminar de verdade: o registro terminal no fim é o do próprio
  supervisor, escrito depois da saída da unidade, e ainda assim não é entregue —
  `indeterminate`, `diverged`, `effects: uncertain`, sem `outcome`.
- A vinculação é publicada fora do diretório que a unidade escreve, e o `start` devolve seu token.
- Um registro só é vinculação quando nomeia os próprios campos: identidade reescrita, autorização
  reescrita e token reescrito são todos lidos como vinculação ausente.
- Job sem vinculação e job com vinculação contrariada não provam fim.
- Nenhum leitor entrega um fim real que não consegue mais conferir (`wait` e `result`, para
  `diverged` e `unanchored`).
- `supervise` recusa reivindicação por quem sua vinculação não responde, sem rodar argv.
- Vinculação que sobreviveu ao diretório de job nunca é sobrescrita.
- Reaproveitamento recusado quando nenhuma vinculação responde pela reivindicação.
- `--expect-binding` conferido por forma antes de qualquer leitura, e o token devolvido por `start`
  entregando a execução para a qual foi devolvido.
- O caso residual em `LeaseBindingTest` nomeia o limite que sobra: uma vinculação reescrita **junto**
  com a reivindicação, por quem tem escrita no diretório de estado inteiro, só é apanhada pelo token.

### Prova por discriminação, em cópia isolada fora do repositório

Cópia de `scripts/tl_job.py` e `tests/test_tl_job.py` fora do repositório, com três defesas
desfeitas, uma por linha: `binding_check` deixa de comparar `lease_identity` (volta a comparar só a
autorização), `read_anchor` deixa de recomputar o token (passa a acreditar no que está escrito) e
`SETTLED_UNPROVABLE` volta a ser `("replaced",)`. As mesmas três classes, nos dois lados:

```
python -m unittest tests.test_tl_job.RewrittenClaimTest tests.test_tl_job.BindingAnchorTest tests.test_tl_job.LeaseBindingTest      (cópia com as defesas desfeitas)
FAIL: test_a_rewritten_claim_is_not_healed_by_the_unit_really_ending
AssertionError: 0 != 5 : {... 'effects': 'known', 'exit_code': 0, 'outcome': 'delivered',
'result_status': 'admitted', 'state': 'exited', 'transport_only': True, 'unit': 'T012'}
FAIL: test_a_unit_that_rewrites_its_claim_still_gets_no_delivery
AssertionError: 'running' != 'diverged'
FAIL: test_a_job_with_no_binding_or_a_contradicted_one_proves_no_ending
FAIL: test_a_record_is_a_binding_only_when_it_names_its_own_fields   (identidade, autorização, token)
FAIL: test_a_reuse_is_refused_when_no_binding_answers_for_the_claim
FAIL: test_no_reader_delivers_a_real_ending_it_can_no_longer_check   (wait e result, 'diverged')
FAIL: test_a_claim_bound_to_nothing_proves_no_ending_either
ERROR: test_a_supervisor_refuses_a_claim_its_binding_does_not_answer_for
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
Ran 20 tests in 18.322s
FAILED (failures=10, errors=1)
(saída 1)

python -m unittest tests.test_tl_job.RewrittenClaimTest tests.test_tl_job.BindingAnchorTest tests.test_tl_job.LeaseBindingTest      (árvore corrigida)
Ran 20 tests in 13.440s
OK
(saída 0)
```

Oito métodos discriminam; os números acima contam subcasos. O `ERROR` do `supervise` é o mesmo sinal
pelo outro lado: sem a vinculação o comando não recusa, segue adiante e não emite recibo algum, e o
caso quebra ao tentar ler o recibo que deveria existir.

Limite declarado, o mesmo das rodadas anteriores: como os dois arquivos não são rastreados, a cópia
desfaz exatamente as defesas desta rodada, não restaura um original recuperado por `git`.

### Honestidade de plataforma

Na linha `AssertionError: 'running' != 'diverged'` está o fato que este host impõe: no Windows,
`os.replace` sobre um lease mantido por descritor aberto é recusado, então, sem a correção, o ataque
completo não chega à entrega **aqui** — para na prova `running` e no `wait` que expira. Quem entrega
neste host é a variante que deixa a unidade terminar: ali a cópia sem as defesas responde saída `0`,
`outcome: delivered`, `effects: known`, sobre uma reivindicação reescrita. Num host onde a troca do
lease passa, as duas variantes entregam. A correção não depende dessa diferença: a reescrita da
reivindicação passa em qualquer plataforma, e é ela que a vinculação responde com `diverged` — por
isso o teste pedido é determinístico dos dois lados.

### Portões, na ordem em que rodaram (host, Windows, offline)

Dirigidos primeiro, as classes da vinculação e a vizinha que guarda o ataque da rodada 20:

```
python -m unittest tests.test_tl_job.BindingAnchorTest tests.test_tl_job.LeaseBindingTest tests.test_tl_job.RewrittenClaimTest tests.test_tl_job.ReplacedLeaseTest
Ran 22 tests in 21.723s
OK
(saída 0)
```

Suíte completa da revisão final:

```
python -m unittest discover -s tests -p "test_*.py"
Ran 154 tests in 397.880s
OK (skipped=3)
(saída 0)
```

Os três pulados são os mesmos das rodadas anteriores, por plataforma (link e permissão POSIX).
Nenhum caso novo desta rodada foi pulado.

```
python scripts/validate_repository.py
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
(saída 0)

git diff --check                        (sem saída, saída 0)
```

`git diff --check` só enxerga arquivo rastreado; `scripts/tl_job.py` e `tests/` continuam `??` e
foram conferidos por leitura direta — LF puro, zero espaço em branco terminal, zero tabulação.

### Limite honesto desta rodada

O alcance da vinculação é o da permissão do sistema de arquivos. Ela protege contra a unidade, que
escreve no próprio diretório de job e não no diretório de estado; não protege contra quem tenha
escrita no diretório de estado inteiro — esse pode reescrever a vinculação junto com a reivindicação
e recompor a coerência de novo. Contra isso só resta o que nunca esteve no disco: o token que o
`start` devolveu, guardado pelo condutor e reapresentado em `--expect-binding`, que recusa a entrega
como `diverged`. O caso residual em `LeaseBindingTest` prova as duas metades desse limite — sem o
token a entrega acontece, com o token ela é recusada. A vinculação também não diz nada sobre o
conteúdo do resultado: ela responde de quem é o diretório, não se o que a unidade produziu está
certo.

## Adendo — a árvore das vinculações também é componente do diretório de estado (rodada 23, 2026-09-12)

Origem: parecer do Checker desta rodada com um único achado, R1: o diretório novo `anchors` não
estava contido por resolução de links no diretório de estado. Um `state-dir/anchors` preexistente
como symlink ou junction para uma árvore externa era aceito, e `write_anchor` escrevia `<unidade>.json`
através dele. A correção pedida: validar `anchors` como componente contido por `realpath` do
`state-dir` **antes** de qualquer diretório de job, lease, manifesto ou vinculação, recusando o
escape com `invalid_input`; mais um teste negativo offline com `anchors` linkado para fora, afirmando
que não há vinculação externa, nem marcador de comando executado, nem reivindicação de job; e a sonda
em cópia isolada onde, removida a checagem nova, o mesmo teste cria a vinculação externa.

Escopo congelado desta rodada: esse único achado, nada além dele. Nenhuma tarefa T001–T011 foi
tocada, nenhum outro achado foi respondido, nenhum serviço, dependência ou credencial foi criado,
nenhum teste existente foi afrouxado, nada saiu para a rede e nenhum commit foi feito por este papel.

O defeito, na forma em que existia: a rodada 18 levou `jobs` e `<state-dir>/jobs/<unidade>` para a
conferência por `realpath` em `job_directory`, mas a rodada 22 criou um componente novo ao lado
deles — `<state-dir>/anchors` — e ele ficou de fora. `write_anchor` só fazia
`check_component(path.parent, "anchors directory")`, que é conferência léxica, e em seguida
`path.parent.mkdir(parents=True, exist_ok=True)`, que aceita o diretório que já existe. Um link
plantado ali antes do primeiro `start` passava nas duas coisas, e a vinculação da unidade — com
`lease_identity`, as duas impressões e o token — era publicada fora do diretório de estado que o
chamador nomeou, sob um nome que ele não escolheu. Pior que o vazamento: quem escrevesse no destino
do link passava a mandar na resposta de `binding_check` para aquela unidade.

### O que mudou

- **`anchors` entra na mesma conferência dos outros componentes, no mesmo lugar.** `job_directory`
  passa a derivar `state_dir / ANCHORS_DIR`, aplicar `check_component` e então
  `contained(anchors, state_dir, ...)`, junto com `jobs` e o diretório da unidade. Não é uma
  checagem nova em `write_anchor`: é a mesma checagem, no ponto de estrangulamento por onde os cinco
  comandos passam antes de qualquer efeito. Por isso ela vale literalmente antes de qualquer
  `mkdir`, lease, manifesto ou vinculação, e vale também para `status`, `wait` e `result`, que não
  escrevem nada.
- **A recusa é `invalid_input`.** Saída `2`, `effects: none`, mensagem
  `anchors directory resolves outside the state directory through a link`, sem argv executado, sem
  diretório de job criado e sem nada escrito no destino do link.
- **Um link contido continua válido.** `anchors` apontando para outra pasta **dentro** da árvore de
  estado resolve para dentro, passa, e a unidade roda e publica a vinculação normalmente. O caminho
  devolvido continua sendo o léxico, então nenhuma identidade muda.
- **Registro.** `docs/EXECUTION_PROTOCOL.md` passa a nomear `<state-dir>/anchors` junto de
  `<state-dir>/jobs/<unidade>` na regra de contenção conferida em todos os comandos, com o motivo —
  a vinculação é publicada por criação do diretório quando ele falta; `CHANGELOG.md` ganhou o item
  correspondente em `### Alterado` de `## [0.8.0] - 2026-09-11`.

### Casos novos em `tests/test_tl_job.py`

Dois casos em `InputTest`, ao lado do par que já cobria `jobs` e a unidade. A árvore atual passa a
ter 156 casos em 31 classes; contagens menores citadas em adendos anteriores descrevem aquelas
rodadas e não esta.

- `test_anchors_component_linked_out_of_the_state_directory_is_refused`: o negativo pedido. O
  `state-dir/anchors` é criado como junction (ou symlink, onde houver privilégio) para
  `outside-anchors`, e o `start` despacha um filho que escreveria um marcador. O caso afirma saída
  `2`, `state: invalid_input`, `effects: none`, mensagem nomeando `anchors directory`, **diretório
  externo vazio** (nenhuma vinculação publicada), **marcador ausente** (o comando não rodou) e
  `<state-dir>/jobs` inexistente (nenhuma reivindicação). Em seguida varre `status`, `wait` e
  `result` pelo mesmo auxiliar já usado pelos casos irmãos, afirmando a mesma recusa e o mesmo
  diretório externo vazio — a recusa vem antes de qualquer escrita, então os leitores respondem
  igual.
- `test_an_anchors_link_that_stays_inside_the_state_directory_still_runs`: a discriminação. Com
  `anchors` linkado para `<state-dir>/real-anchors`, o `start` sai `0`, o `wait` sai `0` e
  `T012.json` aparece no destino contido. A resolução recusa o escape sem recusar o link.

### Prova por discriminação, em cópia isolada fora do repositório

Cópia de `scripts/tl_job.py` e `tests/test_tl_job.py` fora do repositório, com exatamente uma linha
desfeita — a asserção de contenção nova
(`contained(anchors, state_dir, "anchors directory resolves outside the state directory through a link")`),
conferida como presente uma única vez antes de ser removida. O mesmo teste, na cópia:

```
python -m unittest tests.test_tl_job.InputTest.test_anchors_component_linked_out_of_the_state_directory_is_refused -v      (cópia sem a checagem)
FAIL: test_anchors_component_linked_out_of_the_state_directory_is_refused
  File "...\probe-r1\tests\test_tl_job.py", line 642, in test_anchors_...
    self.assertEqual(code, tl_job.EXIT_USAGE)
AssertionError: 0 != 2
Ran 1 test in 0.665s
FAILED (failures=1)
(saída 1)
```

O `0 != 2` é o `start` tendo sucesso. O efeito por trás dele, medido pelo mesmo arranjo fora do
`unittest`, nos dois lados:

```
sonda de efeito, cópia sem a checagem
exit: 0
receipt: {"binding":"e321208896dfdfd4","job_id":"T012","locators":{...},"schema":1,
          "state":"starting","unit":"T012"}
outside anchors dir: ['T012.json']
  content of T012.json -> {"authorization_fingerprint":"a34881fac3889ecd",
  "binding":"e321208896dfdfd4","lease_identity":"134267430143450000:1125899906845389",
  "manifest_fingerprint":"7cf53f36f57ea5e2","schema":1,"unit":"T012"}
job claim exists: True

sonda de efeito, árvore corrigida
exit: 2
receipt: {"effects":"none","error":"anchors directory resolves outside the state directory through a link",
          "job_id":"T012","schema":1,"state":"invalid_input","unit":"T012"}
outside anchors dir: []
job claim exists: False
```

Isto é o achado reproduzido e depois recusado: sem a linha, a vinculação da unidade — identidade do
lease e token inclusive — é publicada em uma árvore que o chamador não nomeou, e a reivindicação é
criada; com a linha, nada aparece lá e nenhum job é reivindicado.

Limite declarado, o mesmo das rodadas anteriores: como os dois arquivos não são rastreados, a cópia
desfaz exatamente a defesa desta rodada, não restaura um original recuperado por `git`.

### Honestidade de plataforma

O link é criado por `mklink /J` (junction de diretório), com `os.symlink` como alternativa onde
houver privilégio: neste host o Windows não concede `SeCreateSymbolicLinkPrivilege` à sessão, e a
junction é o primitivo disponível. Para `os.path.realpath`, junction e symlink de diretório
resolvem igual, que é o que a checagem usa; o caso não depende de qual dos dois foi criado.

### Portões, na ordem em que rodaram (host, Windows, offline)

Dirigidos primeiro, a classe inteira onde os casos novos moram:

```
python -m unittest tests.test_tl_job.InputTest -v
Ran 18 tests in 192.910s
OK (skipped=1)
(saída 0)
```

Suíte completa da revisão final:

```
python -m unittest discover -s tests -p "test_*.py"
Ran 156 tests in 388.689s
OK (skipped=3)
(saída 0)
```

Os três pulados são os mesmos das rodadas anteriores, por plataforma (link e permissão POSIX) —
entre eles o `test_result_file_that_is_itself_a_link_out_of_the_tree_is_refused`, que precisa de
symlink de arquivo. Nenhum caso novo desta rodada foi pulado: os dois usam junction de diretório.

```
python scripts/validate_repository.py
OK: 19 package files; JSON, frontmatter, links, export and hashes validated
NOTE: structural checks do not prove method behavior
(saída 0)

git diff --check                        (sem saída, saída 0)
```

`git diff --check` só enxerga arquivo rastreado; `scripts/tl_job.py` e `tests/` continuam `??` e
foram conferidos por leitura direta — LF puro, zero espaço em branco terminal, zero tabulação.

### Limite honesto desta rodada

A conferência recusa o escape por link **já existente no momento em que ela roda**. Ela não promete
imunidade a corrida de sistema de arquivos que troque `anchors` por um link depois da checagem e
antes do `mkdir` ou do `O_EXCL`, e não enxerga hard link, que não é um componente resolvido por
`realpath`. Também não é uma defesa contra quem já escreve dentro do diretório de estado: esse não
precisa de link nenhum — o limite da rodada 22 continua valendo, e contra ele só o token devolvido
em `binding` e reapresentado em `--expect-binding` recusa a entrega. O que esta rodada fecha é
estreito e verificável: o componente que faltava na contenção agora está lá, e a recusa acontece
antes do primeiro efeito.
