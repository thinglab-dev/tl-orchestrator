id: T027
title: Mandatory Write-Ahead Journaling and Budgeted Dispatch for Automatic Mode
type: feat
deliverable: package
standalone: true
method: native
status: done
state_revision: 2
depends_on: [T018, T026]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-14 (ratificação do Post-Close Audit do B004 e correção de subcontagem e ausência de journaling em despachos de Classifier)
decisions: []
spec_author: orchestrator
spec_revision: d91a27e48b10ca45
rework_round: 0
affects_context: []
effective_authors: [google]
checker_independence: required
content_id: c382a991f801
content_paths: [docs/WORK_MODEL.md, docs/EXECUTION_PROTOCOL.md, prompts/orchestrator.md, prompts/orchestrator-playbook.md, prompts/maker.md, scripts/tl_job.py, scripts/tests/test_automatic_mode.py, CHANGELOG.md]

## Finding
source: auditoria pós-encerramento do lote Canary B004 na Story connector:2-8 do ThingLab Platform em 2026-09-14.
observed: o lote B004 consumiu 9 chamadas reais de modelo (5 Classifiers, 2 Makers, 2 Checkers), mas reportou formalmente apenas 4 chamadas porque os despachos do Classifier foram executados sem gravação de pending_call no frontmatter de Bnnn.md e sem incremento em consumed_model_calls. Além disso, uma tentativa de Classifier que falhou validação de schema não foi contabilizada. O schema batch.schema.json e o cálculo de reserva dinâmica já conhecem o papel classifier, mas a camada operacional do Automatic Mode carecia de um primitive que tornasse estruturalmente impossível invocar qualquer harness de modelo (agy, codex, claude) sem o ciclo formal de write-ahead. Ademais, briefings de Maker instruíram a execução do gate canônico completo (make check) em sandbox isolado sem permissões de socket/rede, violando a política T016 de testes direcionados intragrupo.
expected:
1. Implementar o primitive unificado budgeted_model_dispatch em scripts/tl_job.py, garantindo que todo despacho a harness passe obrigatoriamente por reserve -> pending_call persistido -> dispatch -> resultado observado -> consumed += 1 -> reserved -= 1 -> pending_call = null -> persistência;
2. Cobrir todos os papéis sem exceção (classifier, planner, maker, checker, advisor, searcher);
3. Tratar cada tentativa real de despacho como consumo individual (incluindo retries por schema inválido);
4. Recalcular required_call_reserve antes de qualquer retry, emitindo STOP: insufficient_budget_for_unit_verification caso o saldo restante não cubra o caminho até o Checker independente;
5. Liberar a reserva sem debitar consumed_model_calls quando ocorrer PRE_DISPATCH_UNAVAILABLE;
6. Debitar conservadoramente como consumed e emitir STOP quando o despacho ocorrer mas seu outcome for ambíguo;
7. Incorporar guard explícito nos templates e briefings do Maker para que em etapas intermediárias intragrupo utilize-se exclusivamente testes direcionados (targeted verification), reservando o gate canônico completo para transições de fronteira T016 e fechamento do lote (CLOSE).
impact: elimina completamente a subcontagem de chamadas, impede bypass de journal por qualquer papel e evita falhas espúrias de execução em sandboxes de modelos.
dedup: T018 estabeleceu a máquina de estados e o write-ahead teórico; T027 fecha a lacuna operacional de journaling obrigatório e dispatch orçado.

## Spec
### Intent
Garantir estruturalmente que nenhuma chamada a modelos no Modo Automático possa ocorrer sem o correspondente registro de write-ahead durável em disco, e proteger os agentes executores contra comandos indevidos de full gate em ambientes isolados conforme T016.

### Acceptance criteria
- AC01: budgeted_model_dispatch implementado como primitive unificado que exige persistência prévia de pending_call antes de acionar o harness e atualiza consumed_model_calls e limpa pending_call após o término.
- AC02: Todas as chamadas de Classifier, Maker, Checker, Planner, Advisor e Searcher são registradas e debitadas sem exceção.
- AC03: Retries decorrentes de respostas inválidas (e.g. falha de validação de schema) consomem quota a cada tentativa real. Antes do retry, valida-se a reserva dinâmica restante.
- AC04: PRE_DISPATCH_UNAVAILABLE libera a reserva e limpa pending_call sem consumir chamada.
- AC05: Despachos com resultado ambíguo consomem chamada conservadoramente e interrompem com STOP.
- AC06: Briefings e contratos do Maker instruem testes direcionados intragrupo e vedam a invocação de full gates canônicos em sandbox intermediário.

## Evidence
evidence/T027-r01.md
