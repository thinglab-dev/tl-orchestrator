id: T018
type: feat
deliverable: none
standalone: true
method: native
status: done
state_revision: 2
depends_on: [T017]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-12 (arquitetura do Modo Automático desafiada pelo Advisor e refinada pelo mantenedor)
decisions: []
spec_author: orchestrator
spec_revision: 3c9d4bc09ceeedc0
rework_round: 4
affects_context: []
content_paths: [distribution-manifest.json, README.md, SKILL.md, docs/EXECUTION_PROTOCOL.md, docs/PROJECT_CONFIGURATION.md, docs/WORK_MODEL.md, prompts/orchestrator.md, prompts/orchestrator-playbook.md, schemas/batch.schema.json, scripts/tests/test_automatic_mode.py, scripts/tests/test_advisor_policy.py, CHANGELOG.md]
content_id: c17af9685cc5b1601b5f2871b204a053a27fb63b:b2038b1060335089
effective_authors: [openai, google, anthropic]
checker_independence: preferred

## Finding
source: consulta consultiva ao papel Advisor em 2026-09-12 (parecer `adjust` validado, com 7 achados dispostos integralmente) e alinhamento estratégico com o mantenedor incorporando contribuições materiais OpenAI, Google e Anthropic.
observed: o tl-orchestrator possui mecanismos robustos de espera/liveness (T013), roteamento e independência (T014), economia de contexto (T015), cadência de verificação (T016) e desafio consultivo por Advisor (T017), mas carece de uma governança unificada para execução autônoma contínua. Sem uma especificação estrita, tentativas de "modo automático" arriscam agentes indefinidamente autônomos, loops de polling, queima descontrolada de chamadas sem saldo para revisão, drifts de autoridade e falta de recuperação auditável.
expected: formalizar o Modo Automático com escopo estreito e salvaguardas estritas:
1. Máquina de estados formal: `IDLE → DISCOVER → PROPOSE → WAIT_AUTHORIZATION → PREFREEZE_REVALIDATE → FREEZE_BATCH → EXECUTE → CLOSE`;
2. Invariante de autorização: o comando inicial autoriza exclusivamente a fase de leitura (`DISCOVER → PROPOSE`); a execução exige autorização humana explícita antes do congelamento do lote;
3. Aprovação parcial sempre reproposta com novo digest;
4. Revalidação pré-freeze contra drift durante a espera humana (`PREFREEZE_REVALIDATE`);
5. Persistência híbrida durável: entidade Batch em `_tl-orc/project/batches/Bnnn.md` como autoridade de escopo e progresso, e `STATUS.md` como projeção leve e mutex de coordenação;
6. Rejeição formal de lote apenas em memória (*runtime-only*);
7. Contabilidade observável de chamadas por reserva write-ahead lógica sob coordenador (`reserved → pending_call → dispatch → consumed`), com resolução conservadora em interrupções ambíguas;
8. Admission gate por unidade e reserva mandatória dinâmica de orçamento cobrindo todo o caminho obrigatório até o Checker (`insufficient_budget_for_unit_verification`);
9. Simetria de `bad_spec_or_intent_gap` antes e depois do Maker;
10. Retrabalho automático estritamente restrito a correções de Maker dentro da spec/content_paths/budget congelados;
11. 18 condições formais de parada (*stop conditions*);
12. Composição semântica com T013–T017 (esperas, independência, economia de contexto, portões de fronteira em cada transição de grupo dentro do lote e Advisor não-recursivo);
13. Invariante terminal: lote concluído nunca cria outro lote automaticamente;
14. Governança de independência de T018: autoria acumulada `[openai, google, anthropic]`, operando sob `checker_independence: preferred` com registro de limitação na evidência por inexistência de quarta família.
impact: confere ao tl-orchestrator a capacidade de executar autonomamente lotes de tarefas previamente aprovadas com total segurança contra deriva de escopo, auto-autorização, loops infinitos, estouro orçamentário e regressões de qualidade.
hypothesis: a especificação explícita dos contratos em `docs/WORK_MODEL.md`, `prompts/orchestrator.md`, `prompts/orchestrator-playbook.md`, `docs/PROJECT_CONFIGURATION.md`, `schemas/batch.schema.json` e uma suíte de testes determinísticos em `test_automatic_mode.py` garante execução auditável, segura e recuperável em qualquer ambiente.
dedup: T010 fixou condução e escalonamento; T011/T013 definiram regras preliminares de lote e esperas; T014 formalizou participantes e perfis; T015 normatizou economia de contexto; T016 estabeleceu a cadência de verificação e portões de fronteira; T017 introduziu o desafio estratégico por Advisor; T018 unifica e conclui a arquitetura operacional do Modo Automático.

## Spec
### Intent
Permitir a execução autônoma de um lote finito e explicitamente autorizado de unidades já conhecidas do projeto, preservando integralmente a autoridade humana exclusiva sobre escopo, orçamento e efeitos externos; o congelamento estrito de escopo e membresia no momento do freeze; a contabilidade garantida de orçamento que impede a criação de patches órfãos sem saldo para verificação independente; a aplicação rigorosa de portões de fronteira T016 a cada transição de grupo dentro do lote; e a recuperação auditável a partir de persistência híbrida em disco.
T018 não cria daemon, transação distribuída, engine autônomo persistente, lock distribuído ou atomicidade de banco de dados: o Modo Automático é um protocolo durável conduzido pelo Orchestrator/harness existente através de uma disciplina documental de write-ahead serializada pelo coordinator.

### Scope and write paths
- distribution-manifest.json: ampliação do manifesto de pacote para 22 arquivos canônicos, incluindo schemas/batch.schema.json, docs/EXECUTION_PROTOCOL.md e scripts/tl_job.py.
- README.md: sincronização das contagens de arquivos para 22, atualização dos manifestos legíveis, blocos de exportação e comandos de verificação de checksums.
- SKILL.md: inclusão das regras normativas, ciclo de vida e comandos do Modo Automático na seção de contratos e no roteamento de ativação.
- docs/EXECUTION_PROTOCOL.md: especificação da subseção de execução sob Modo Automático, integrando o despacho por artefatos com o consumo de recibo terminal compacto (< 4 KiB) pelo condutor do lote.
- docs/PROJECT_CONFIGURATION.md: especificação da infraestrutura de batches em _tl-orc/project/batches/, campos de projeção em STATUS.md (active_batch, batch_status, next_batch_id) e relacionamento com a fila sequencial.
- docs/WORK_MODEL.md: formalização completa do Modo Automático, máquina de estados formal, envelope estruturado de batches/Bnnn.md, write-ahead lógico serializado, admission gate por unidade com reserva dinâmica, composição formal com docs/EXECUTION_PROTOCOL.md (e scripts/tl_job.py), aplicação de portões T016 em cada transição interna de integration_group, 18 stop conditions, semântica de aprovação parcial e rejeição formal de runtime-only.
- prompts/orchestrator.md: diretrizes centrais do Modo Automático, princípio fundamental ("iniciar modo automático" autoriza apenas DISCOVER → PROPOSE, nunca execução) e vedações operacionais.
- prompts/orchestrator-playbook.md: roteiro operacional passo a passo para orquestração de batches (DISCOVER, PROPOSE, WAIT_AUTHORIZATION, PREFREEZE_REVALIDATE, FREEZE_BATCH, loop EXECUTE e CLOSE), tratamento de aprovação parcial e recuperação pós-interrupção.
- schemas/batch.schema.json: novo schema JSON estrito Draft 2020-12 validando o envelope estruturado / frontmatter YAML de _tl-orc/project/batches/Bnnn.md, distinguindo o snapshot imutável de autoridade/escopo (vinculado a immutable_digest) das seções mutáveis de progresso da execução.
- scripts/tests/test_automatic_mode.py: nova suíte de testes contratuais determinísticos e contrafactuais validando os estados, gates de admissão, reserva dinâmica, revalidação pré-freeze, persistência híbrida, transições de fronteira T016 dentro do lote, write-ahead e stop conditions.
- scripts/tests/test_advisor_policy.py: alinhamento do consumidor contratual de T017 para validar a paridade dinâmica do manifesto e a integridade dos artefatos próprios de T017 sem hardcode incidental de contagem fixa, preservando a suíte contratual perante a expansão para 22 arquivos canônicos.
- CHANGELOG.md: registro formal da introdução do Modo Automático na distribuição sob [Unreleased].

### Acceptance criteria
- AC01 (Fronteira de autoridade): O comando "iniciar modo automático" autoriza estrita e exclusivamente a fase de leitura DISCOVER → PROPOSE. Nenhuma alteração de arquivos, commit ou despacho de agentes de implementação é permitida sem autorização humana explícita prévia sobre a proposta estruturada.
- AC02 (Máquina de estados formal): Implementação da máquina de estados IDLE → DISCOVER → PROPOSE → WAIT_AUTHORIZATION → PREFREEZE_REVALIDATE → FREEZE_BATCH → EXECUTE → CLOSE, com saídas excepcionais BLOCKED, STOPPED, FAILED e CANCELLED.
- AC03 (Semântica de aprovação parcial): A aprovação humana de um subconjunto de unidades propostas nunca filtra o freeze diretamente; gera obrigatoriamente um novo ciclo PROPOSE com recálculo de dependências, orçamentos, boundaries de integração e proposal_digest para nova confirmação explícita.
- AC04 (Revalidação pré-freeze): No estado PREFREEZE_REVALIDATE, imediatamente antes do freeze em disco, recalculam-se e revalidam-se síncronamente revisões das unidades, spec_revisions, dependências, scope_digest e efeitos autorizados. Qualquer divergência ou drift invalida a proposta anterior e retorna obrigatoriamente a PROPOSE, sendo vedada adaptação silenciosa.
- AC05 (Persistência híbrida durável): Adoção de _tl-orc/project/batches/Bnnn.md como fonte autoritativa do lote e _tl-orc/project/STATUS.md como projeção leve (active_batch, batch_status, next_batch_id) e lock de coordenação da árvore. schemas/batch.schema.json valida o frontmatter estruturado de Bnnn.md, separando o snapshot imutável de autoridade/escopo (vinculado a immutable_digest) do progresso mutável (status, budget, current_unit, pending_call, checkpoints). Em divergência, Bnnn.md prevalece.
- AC06 (Rejeição formal de runtime-only): A Alternativa C (lote apenas em memória) é formalmente desqualificada e rejeitada por violar a durabilidade e a recuperação auditável exigidas pelo método.
- AC07 (Contabilidade por write-ahead lógico): O controle orçamentário baseia-se em chamadas efetivamente realizadas observadas, operado via write-ahead lógico serializado pelo coordenador (verificar saldo → reservar slots → pending_call → despachar → observar receipt → converter reserved em consumed → limpar pending_call).
- AC08 (Recuperação auditável pós-interrupção): Na retomada pós-crash, o estado do lote é revalidado; caso exista pending_call sem evidência inequívoca de conclusão, contabiliza-se conservadoramente como consumed e interrompe-se com STOP, impedindo estouro silencioso de orçamento.
- AC09 (Admission gate por unidade): Antes de admitir qualquer unidade em EXECUTE, revalidam-se autoridade inalterada, membresia congelada no snapshot, integridade de revisões/specs, dependências satisfeitas (status == done), coordenador válido, estado da árvore (tree_state == expected_checkpoint), efeitos permitidos e saldo orçamentário.
- AC10 (Reserva dinâmica de orçamento por ciclo completo): A reserva mandatória de orçamento não é um número fixo universal, sendo calculada dinamicamente: required_call_reserve = todas as chamadas obrigatórias ainda não consumidas do checkpoint atual até o Checker independente (incluindo Classifiers de cada fase, Maker, Checker e, quando já exigidos, Planner ou Advisor). Antes de iniciar nova unidade ou retrabalho (rework), saldo inferior a required_call_reserve dispara imediatamente STOP: insufficient_budget_for_unit_verification. (Os valores 4/3/4 constituem exemplos típicos do fluxo comum, nunca constantes normativas).
- AC11 (Simetria de bad_spec_or_intent_gap): A sinalização de incerteza material insolúvel, especificação inconsistente ou lacuna de intenção opera simetricamente: se levantada pelo Classifier da fase ou por validação prévia, interrompe a unidade antes de despachar o Maker; se levantada pelo Checker, interrompe antes de autorizar retrabalho automático.
- AC12 (Limites estritos de retrabalho automático): O avanço automático em changes_requested é restrito a achados direcionados ao Maker, contidos na spec_revision e content_paths congelados, sem alteração de produto ou arquitetura, e dispondo de saldo para todo o ciclo restante de rework até o re-review independente.
- AC13 (18 Stop conditions formais): Interrupção imediata da execução sob qualquer uma das 18 condições formais catalogadas, com comportamento padrão dependency_block configurado como continue_independent_after_block: false.
- AC14 (Composição com T012–T017 e vedações de Advisor): Integração semântica com o protocolo de execução por artefatos e recibos terminais compactos de docs/EXECUTION_PROTOCOL.md (T012/PR #45), esperas mecânicas (T013), seleção de perfis e independência (T014), context economy (T015), cadência de verificação T016 e acionamento estrito de Advisor por gatilhos objetivos (T017), com vedações explícitas contra recursão de Advisor e débito mandatório em max_advisor_calls.
- AC15 (Fronteiras de integração T016 dentro do lote): Um único lote pode atravessar múltiplos integration_groups. O canonical_full_gate oficial deve ser executado obrigatoriamente em cada transição de integration_group dentro do batch, além do fechamento do último grupo antes de batch_status = done (CLOSE). O fechamento do lote nunca gera nem dispara outro lote automaticamente.
- AC16 (Autoria material acumulada e governança de independência de T018): Registro formal de effective_authors: [openai, google, anthropic] na Task T018; operação sob checker_independence: preferred com registro de limitação na evidência por inexistência de uma quarta família no catálogo atual, vedando-se checker_independence: required.
- AC17 (Suíte contratual e validação estrutural): Implementação de scripts/tests/test_automatic_mode.py cobrindo deterministicamente AC01 a AC16, preservação das suítes contratuais T016 (test_verification_cadence.py) e T017 (test_advisor_policy.py) perante a expansão do manifesto, e validação com python3 scripts/validate_repository.py cobrindo os 22 arquivos de pacote da distribuição canônica.

## Verification profile
feat: execução da suíte contratual determinística `scripts/tests/test_automatic_mode.py`, testes de regressão de T016 (`test_verification_cadence.py`) e T017 (`test_advisor_policy.py`), e validação estrutural do repositório (`python3 scripts/validate_repository.py`).

## Plan
1. ➖ Rascunho arquitetural v0 e challenge packet desafiados pelo Advisor independente Claude (Anthropic): concluído com parecer `adjust` e 7 achados ratificados e dispostos no documento `advisor-disposition.md`.
2. ➖ Rascunho arquitetural v1 consolidado e formalização de T018 em `ready`: estado atual com os 5 refinamentos do mantenedor incorporados.
3. ➖ Implementação dos contratos, schemas, prompts, documentação e testes nos 10 `content_paths` (autorizada pelo mantenedor após freeze de spec_revision).
4. ➖ Execução da suíte direcionada `test_automatic_mode.py` e validação estrutural.
5. ➖ Classificação de review e despacho de Checker independente sob `checker_independence: preferred`.
6. ➖ Execução do `canonical_full_gate` de fronteira e fechamento de T018.

## Result

## Evidence

## Review
