id: T019
type: feat
deliverable: none
standalone: true
method: native
status: ready
state_revision: 0
depends_on: [T018, T024]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-13 (formalização da seleção dinâmica de primário T019 com R1 a R22)
decisions: []
spec_author: orchestrator
spec_revision: cefc2cfbaba4944c
rework_round: 0
affects_context: []
content_paths: [distribution-manifest.json, README.md, SKILL.md, docs/PROJECT_CONFIGURATION.md, docs/WORK_MODEL.md, prompts/classifier.md, prompts/orchestrator.md, prompts/orchestrator-perfis.md, schemas/classification-result-v3.schema.json, scripts/validate_classification.py, scripts/tests/test_dynamic_primary_selection.py, scripts/tests/test_automatic_mode.py, CHANGELOG.md]
content_id: unknown até a implementação
effective_authors: [openai, google, anthropic]
checker_independence: preferred

## Finding
source: validação hold-out empírica (Stories 5-5, 6-5, 10-1) concluída em 2026-09-13 e alinhamento normativo com o mantenedor incorporando os requisitos contratuais R1 a R22.
observed: no tl-orchestrator v0.8.0 / schema v2, a tabela de cadeias em _tl-orc/PROJECT.md confunde ranking de qualidade com fallback de infraestrutura. O Classificador é forçado a devolver candidatos na ordem física da cadeia e o Orquestrador despacha incondicionalmente candidates[0], impedindo que um modelo de outro harness (ex.: gpt-5.6-terra no Codex ou gemini no Agy) seja selecionado como primário mesmo quando for tecnicamente superior ou economicamente mais adequado. Além disso, a validação empírica revelou desempates indeterminados não formalizados e risco de corrupção de workspace caso um Maker secundário seja despachado após falha ambígua do primeiro.
expected: formalizar a Task T019 separando estritamente decisão semântica (quem DEVERIA executar) de despacho operacional (quem PODE executar) e de recuperação de infraestrutura (side-effect safe fallback):
1. Classificador seleciona o primary_candidate por mérito técnico e custo comprovado em candidates[0], avaliando simultaneamente todos os pares autorizados cross-harness;
2. Minimum Technical Adequacy Gate (R10): candidatos insuficientes permanecem em evaluations[] com dispatchable=false e NUNCA são promovidos a fallback;
3. Schemas separados e sem redundância (R6, R12, R18, R19): schemas/classification-result-v3.schema.json novo e schemas/classification-result.schema.json v2 preservado; evaluations[] granular por par (harness, model, effort) auditando technical_adequacy (sufficient|insufficient|uncertain), evidence_ids e uncertainty; candidates[] como autoridade única de ranking; matriz de estados fechada (conclusive, underdetermined, awaiting_operator, infeasible);
4. Desempate determinístico harmonizado (R1, R2, R8, R11, R13, R16, R20): empate com vencedor único por política automática resulta em underdetermined; política ask ou política automática sem vencedor único resulta em awaiting_operator; sem viés contra unknown; minimal effort restrito ao mesmo modelo; distinção entre unit_token_price e expected_task_cost;
5. Separação semântica vs despacho (R3, R17, R21): quota_pressure não altera ranking semântico; preflight puramente local (zero slots); preflight remoto/CLI como tentativa formal contabilizada;
6. Side-Effect Safe Fallback Machine (R5, R14, R15, R22): 4 classes de resultado de despacho compondo com EXECUTION_PROTOCOL e T018; bloqueio absoluto de fallback diante de DISPATCH_OUTCOME_AMBIGUOUS (STOP imediato); write-ahead mandatória de slot e respeito à reserva dinâmica required_call_reserve(current_checkpoint);
7. Independência graduada (R4): checker_independence e advisor_independence respeitam preferred (mesma família como fallback degradado devidamente marcado) vs required (bloqueio);
8. Rollout opt-in e compatibilidade dual (R9): classification_schema_version: 2 preserva integralmente o pipeline e schema legados; classification_schema_version: 3 ativa a semântica dinâmica de T019; novo validador canônico scripts/validate_classification.py suporta ambos os contratos.
impact: confere ao tl-orchestrator a capacidade de selecionar dinamicamente o melhor modelo global entre todas as famílias autorizadas para cada fase da Story, eliminando o favoritismo estático de cadeias físicas sem comprometer a estabilidade orçamentária nem a integridade do repositório.
hypothesis: a separação formal entre ranking semântico, disponibilidade operacional de despacho e recuperação de infraestrutura orientada a artefatos e ledgers de efeito garante escalabilidade multi-harness segura e determinística.
dedup: T014 formalizou a política de participantes; T017 introduziu o Advisor cross-family; T018 consolidou o Modo Automático e a contabilidade write-ahead; T019 desacopla o ranking de qualidade da cadeia física de fallback.

## Spec
### Intent
Desacoplar formalmente a avaliação semântica de qualidade do Classificador da cadeia física de fallback de infraestrutura, permitindo que o Classificador eleja como primário recomendado qualquer par modelo/effort autorizado no catálogo (cross-harness), enquanto o Runtime governa a disponibilidade factual no momento do despacho e a recuperação de falhas estritamente segura contra efeitos colaterais.

### Scope and write paths
- distribution-manifest.json: ampliação do manifesto de distribuição para registrar os novos arquivos canônicos do pacote (schemas/classification-result-v3.schema.json e scripts/validate_classification.py), derivando dinamicamente a contagem final de package_file_count a partir dos package_files registrados (de 22 para 24 arquivos).
- README.md: documentação do suporte ao Schema v3 e da separação entre ranking semântico e fallback de infraestrutura.
- SKILL.md: atualização dos contratos de roteamento de modelos e das diretrizes operacionais de despacho e fallback.
- docs/PROJECT_CONFIGURATION.md: especificação dos campos de configuração routing.underdetermined_tiebreak, routing.tie_break_priority e classification_schema_version (v2 vs v3).
- docs/WORK_MODEL.md: especificação da máquina de estados de fallback side-effect safe (4 classes de despacho), integração com write-ahead de orçamento e preservação da reserva dinâmica required_call_reserve(current_checkpoint) de T018.
- prompts/classifier.md: atualização do prompt para modo v3 (avaliação granular cross-harness, minimum technical adequacy gate, matriz de estados e desempate determinístico).
- prompts/orchestrator.md: formalização da separação entre recommended_primary (semântico) e effective_primary (despacho factual), regras de preflight local vs remoto e bloqueio de fallback em DISPATCH_OUTCOME_AMBIGUOUS.
- prompts/orchestrator-perfis.md: remoção da semântica de "ordem de preferência" das tabelas de cadeias, redefinindo-as como conjuntos de elegibilidade e fallback de emergência.
- schemas/classification-result-v3.schema.json [NEW]: novo schema Draft 2020-12 validando a matriz de 4 estados (conclusive, underdetermined, awaiting_operator, infeasible), evaluations granular por par e candidates como autoridade única de ranking. O schema v2 legado (schemas/classification-result.schema.json) permanece inalterado para compatibilidade opt-in.
- scripts/validate_classification.py [NEW]: novo validador canônico upstream (distribuído no pacote), responsável pelo dispatch e validação formal de contratos de classificação v2 e v3 com base em classification_schema_version.
- scripts/tests/test_dynamic_primary_selection.py [NEW]: nova suíte de testes determinísticos cobrindo seleção de Codex/Agy como primário, tie-break determinístico sem viés contra unknown, minimum technical adequacy gate, preflight local vs remoto, auditoria EXECUTION_PROTOCOL e prevenção de fallback ambíguo de Maker.
- scripts/tests/test_automatic_mode.py: ajuste durável da asserção de integridade do manifesto herdada de T018 (paridade entre package_file_count e len(package_files), preservando as garantias e presenças contratuais de artefatos da T018 sem hardcode incidental da contagem global do pacote).
- CHANGELOG.md: registro formal da introdução da Seleção Dinâmica de Primário (T019) sob [Unreleased].

### Invariants (R1 a R22)
- R1 (Unknown Handling): cost_basis: unknown nunca perde um desempate econômico; a relação com custo conhecido é estritamente economic comparison unavailable.
- R2 (Minimal Effort Restrito): menor esforço (medium < high) só desempata dentro do mesmo modelo ou quando houver evidência empírica catalogada de equivalência cross-model.
- R3 (Desacoplamento de Quota): quota_pressure não contamina o ranking semântico durável do Classificador; atua exclusivamente no Runtime no instante do despacho (effective_primary).
- R4 (Independência Preferred vs Required): required bloqueia famílias autoras antes do ranking; preferred prioriza famílias independentes mas admite same-family como fallback degradado explicitamente marcado (degraded_same_family: true).
- R5 (Fallback Side-Effect Safe): 4 classes formais de despacho (PRE_DISPATCH_UNAVAILABLE, DISPATCH_FAILED_PROVEN_NO_EFFECT, DISPATCH_OUTCOME_AMBIGUOUS, SEMANTIC_FAILURE). Fallback automático é terminantemente proibido diante de DISPATCH_OUTCOME_AMBIGUOUS (gera STOP imediato).
- R6 (Schema v3 Sem Redundância): candidates[] é a única autoridade canônica de ranking; candidates[0] é o recommended_primary em estados resolvíveis; elimina chaves independentes redundantes.
- R7 (Exclusão de Null de Candidates): pares sem modelos autorizados no catálogo são restritos a evaluations[] (eligible: false) e terminantemente excluídos de candidates[].
- R8 (Harmonização de Desempate Indeterminado): diante de empate semântico em que a base econômica é incomparável ou idêntica, se a política automática do projeto (project_priority ou legacy_chain) obtiver um vencedor único, emite selection_status: underdetermined, tie_break_applied != null e define exatamente 1 primário (candidates[0]), sem inventar superioridade técnica. Se a política for ask ou se a política automática for incapaz de obter um vencedor único (exaustão ou ambiguidade), transiciona para selection_status: awaiting_operator (R11).
- R9 (Rollout Opt-In Dual): classification_schema_version: 2 seleciona pipeline legado integral com schemas/classification-result.schema.json; classification_schema_version: 3 ativa pipeline T019 com schemas/classification-result-v3.schema.json; validador canônico scripts/validate_classification.py suporta ambos via schema_version.
- R10 (Minimum Technical Adequacy Gate): apenas candidatos com technical_adequacy == "sufficient" são admitidos em candidates[] (dispatchable: true); pares insuficientes permanecem em evaluations[] e nunca viram fallback.
- R11 (Representação de awaiting_operator): diante de empate semântico sob política ask ou sob política automática sem vencedor único (exaustão da lista de seletores sem match ou múltiplos matches não-unívocos), emite selection_status: awaiting_operator, todos os candidatos com dispatch_role: "unassigned", zero primário, e dispara STOP / AWAIT_AUTHORIZATION no Runtime.
- R12 (Evaluations por Candidate Pair): avaliação individual de cada par (harness, model, effort) catalogado, registrando catalog_eligible, technical_adequacy (sufficient|insufficient|uncertain), dispatchable, evidence_ids, uncertainty e reason.
- R13 (Sintaxe Granular de project_priority): seletores determinísticos com suporte a desempate cross-model e intra-família (harness/model/effort > harness/model/* > harness/*).
- R14 (Proven No Effect Robusto): DISPATCH_FAILED_PROVEN_NO_EFFECT exige cumulativamente process-tree terminal, checkpoint git limpo, content_paths intocados e ausência comprovada de efeitos colaterais externos via EXECUTION_PROTOCOL.
- R15 (Budget e Write-Ahead de Fallback): toda tentativa reserva 1 slot no journal antes do despacho; tentativa abortada/ambígua conta como consumida; fallback só ocorre se houver saldo restante autorizada no lote.
- R16 (Semântica Econômica Precisa): token_price_only suporta exclusivamente unit_token_price; proibido alegar expected_task_cost menor sem proxy oficial ou medição empírica observada.
- R17 (Preflight de Harness Genérico): conceito normativo harness capability available at preflight abrangendo integridade de CLI, autenticação/sessão, conectividade e cotas ativas.
- R18 (Matriz de Estados Fechada):
  * conclusive: candidates >= 1, exatamente 1 primary (candidates[0]), zero unassigned, tie_break_applied: null.
  * underdetermined: empate semântico resolvido por política automática (project_priority ou legacy_chain) com vencedor único, candidates >= 1, exatamente 1 primary (candidates[0]), tie_break_applied != null, reason declara primário por política.
  * awaiting_operator: empate semântico sob política ask ou política automática sem vencedor único, candidates >= 2, todos dispatch_role: unassigned, zero primary, Runtime dispara STOP / AWAIT_AUTHORIZATION.
  * infeasible: nenhum par atingiu adequação mínima (technical_adequacy: "sufficient"), candidates: [], Runtime dispara STOP / RECLASSIFY.
- R19 (Adequação Técnica Auditável): technical_adequacy tipado como sufficient, insufficient ou uncertain, acompanhado de evidence_ids e uncertainty justificando formalmente a classificação.
- R20 (Matcher Determinístico de Prioridade): para cada seletor na ordem: 0 matches -> ignora; 1 match -> vencedor; >1 matches -> não resolve e continua; fim da lista sem vencedor único -> awaiting_operator (zero desempate lexical, de catálogo ou posicional oculto).
- R21 (Local vs Remote Preflight): preflight puramente local e sem requests falha sem consumir slot (reservation released); preflight remoto ou invocação de CLI constitui tentativa formal (write-ahead, slot consumido e auditoria EXECUTION_PROTOCOL).
- R22 (Dynamic Budget Reserve de T018): fallback só é admitido se remaining_budget >= fallback_attempt_cost + required_call_reserve(current_checkpoint), preservando integralmente as chamadas necessárias para fechar o lote com Checker independente.

### Acceptance criteria
- AC01 (Seleção Dinâmica de Primário): O Classificador é capaz de eleger como recommended_primary qualquer par modelo/effort autorizado no catálogo (Codex, Claude ou Agy), governado por technical_adequacy e evidências econômicas, sem subordinação à ordem ordinal de chains.
- AC02 (Contrato Schema v3 Formalizado): Implementação do novo schemas/classification-result-v3.schema.json validando rigorosamente a matriz de 4 estados (conclusive, underdetermined, awaiting_operator, infeasible), evaluations granular por par e candidates ordenado, preservando schemas/classification-result.schema.json inalterado para v2.
- AC03 (Minimum Technical Adequacy Gate): Pares avaliados com technical_adequacy: insufficient ou uncertain recebem dispatchable: false em evaluations[] e são estritamente excluídos de candidates[], impedindo promoção indevida a fallback de infraestrutura.
- AC04 (Estado awaiting_operator e Parada): Configuração underdetermined_tiebreak: ask ou política automática sem vencedor único (exaustão ou múltiplos matches) produz selection_status: awaiting_operator com dispatch_role: unassigned, zero primário e dispara STOP / AWAIT_AUTHORIZATION no Runtime.
- AC05 (Matcher Determinístico de project_priority): O desempate por seletor do projeto opera estritamente por regra de unicidade (1 match vence; 0 ou >1 continua; exaustão gera awaiting_operator), sem recurso a ordem alfabética ou do catálogo.
- AC06 (Side-Effect Safe Fallback Machine): O Runtime classifica desfechos em 4 classes e bloqueia terminantemente fallback automático diante de DISPATCH_OUTCOME_AMBIGUOUS (disparando STOP imediato e preservando workspace dirty para reconciliação humana).
- AC07 (Auditoria Robusta Proven No Effect): A autorização de fallback em DISPATCH_FAILED_PROVEN_NO_EFFECT exige comprovação cumulativa de término de process-tree, integridade de checkpoint git, invariância de content_paths e zero efeitos externos via EXECUTION_PROTOCOL.
- AC08 (Composição Orçamentária com T018): Toda tentativa de despacho registra write-ahead; tentativas ambíguas são debitadas; fallback é condicionado à preservação da reserva dinâmica required_call_reserve(current_checkpoint).
- AC09 (Disciplina de Preço Unitário vs Custo Total): O contrato e prompt distinguem unit_token_price de expected_task_cost, proibindo alegações de custo total inferior da tarefa fundamentadas puramente em token_price_only.
- AC10 (Validador Dual Upstream e Rollout Opt-In): Novo scripts/validate_classification.py adicionado à distribuição canônica suportando nativamente v2 e v3 com base em classification_schema_version, assegurando zero impacto regressivo em projetos consumidores v0.8.0.
- AC11 (Preservação de Consumidores Contratuais do Manifesto): A ampliação de distribution-manifest.json por T019 preserva os consumidores contratuais existentes que validam a integridade do manifesto, em particular scripts/tests/test_automatic_mode.py herdado de T018, que reconfirma dinamicamente package_file_count == len(package_files) e a presença contratual dos artefatos de T018 (schemas/batch.schema.json, docs/EXECUTION_PROTOCOL.md, scripts/tl_job.py) no manifesto ampliado, sem qualquer hardcode incidental da contagem global do pacote.

### State machine de fallback seguro e recuperação
A execução de despacho compõe o protocolo de execução (docs/EXECUTION_PROTOCOL.md) com a contabilidade do Modo Automático (T018):
1. Verificação de Saldo: remaining_budget >= 1 + required_call_reserve(current_checkpoint). Se falso, STOP SC04.
2. Reserva Lógica (Write-Ahead): Gravação de slot pendente no journal (status: pending_dispatch).
3. Preflight Local (R21): Inspeciona executáveis no PATH, arquivos de configuração e credenciais locais estáticas. Se falhar, classifica como PRE_DISPATCH_UNAVAILABLE, cancela a reserva (reservation released) e avança para o próximo candidato.
4. Tentativa de Despacho (Remote / Process): Se exigir request ou CLI, o slot é formalmente comprometido. Dispara subprocesso via tl_job.py / EXECUTION_PROTOCOL.
5. Sucesso Limpo: Processo encerra com código 0 e recibo terminal válido (< 4 KiB). Converte reserved em consumed.
6. Falha Operacional: Processo sofre timeout, crash (SIGKILL/SIGSEGV) ou recusa 429 persistente. O slot é debitado como consumed.
7. Auditoria Imediata de Efeitos (R14):
   - Se process-tree for terminada, git status --porcelain limpo, content_paths inalterados e sem efeitos de rede -> DISPATCH_FAILED_PROVEN_NO_EFFECT. Se houver saldo e reserva dinâmica restante, avança para o próximo candidato de fallback.
   - Se houver arquivos modificados, untracked files ou incerteza -> DISPATCH_OUTCOME_AMBIGUOUS. O Runtime emite STOP imediato (SC17), congela o lote e proíbe fallback.
8. Falha Semântica: Código falha em testes ou Checker emite findings. Não aciona fallback; entra no loop de Rework ou Reclassificação.

### Exemplos canônicos de especificação e comportamento
1. Cenário 1 (Codex Semantic Primary): Desenvolvimento em Go nativo de baixo nível. Classificador avalia gpt-5.6-terra/medium com technical_adequacy: sufficient ancorado em gpt56-coding e menor unit_token_price (price-terra). Eleito recommended_primary; Claude Sonnet High figura como fallback.
2. Cenário 2 (Claude Semantic Primary): Ingestão relacional complexa com PII. Sonnet Medium é avaliado como technical_adequacy: insufficient pelo risco de integridade e recebe dispatchable: false (excluído de candidates). Sonnet High é eleito recommended_primary; Codex Terra Medium figura como fallback.
3. Cenário 3 (Underdetermined + project_priority): Sonnet High e Fable High empatam; custo de Fable é unknown (comparação econômica indisponível). Classificador marca selection_status: underdetermined e aplica seletor granular claude/sonnet/high da política do projeto, sem alegar superioridade técnica sobre Fable.
4. Cenário 4 (Preflight de Harness Indisponível): Recommended primary (Codex) falha no preflight local por CLI ausente. Classificado como PRE_DISPATCH_UNAVAILABLE, zero slots debitados, e fallback Claude é acionado com segurança.
5. Cenário 5 (Timeout Ambíguo de Maker): Maker A (Agy) sofre timeout de rede e deixa 2 arquivos modificados no disco. Runtime classifica como DISPATCH_OUTCOME_AMBIGUOUS, debita 1 chamada consumida e emite STOP SC17 imediato, impedindo que o Maker B (Codex) sobrescreva a árvore dirty.

### Estratégia de testes contratuais e determinísticos
A suíte scripts/tests/test_dynamic_primary_selection.py cobrirá:
1. Validação estrita do schema Draft 2020-12 (schemas/classification-result-v3.schema.json) contra a matriz completa de 4 estados.
2. Teste contrafactual de Minimum Technical Adequacy Gate: verificação de que candidatos com technical_adequacy: insufficient ou uncertain jamais aparecem em candidates[].
3. Teste determinístico do matcher de project_priority: resolução exata por seletor único, continuidade diante de múltiplos matches e transição para awaiting_operator em caso de exaustão.
4. Teste de isolamento de quota: verificação de que quota_pressure não altera recommended_primary e é aplicado apenas em runtime.
5. Teste contrafactual de segurança de Maker: simulação de processo falho com árvore dirty garantindo emissão de STOP e bloqueio de fallback.
6. Teste de controle orçamentário write-ahead: garantia de que tentativas falhas debitam saldo e que a reserva dinâmica T018 impede fallbacks que deixariam a Story sem saldo para Checker.
7. Teste de compatibilidade dual: execução de scripts/validate_classification.py validando fixture v2 (ordem estática) e fixture v3 (ranking dinâmico).
8. Verificação durável de paridade do manifesto em consumidor contratual existente (scripts/tests/test_automatic_mode.py, herdado de T018): reconfirmação de que package_file_count == len(package_files) e da presença contratual dos artefatos de T018 (schemas/batch.schema.json, docs/EXECUTION_PROTOCOL.md, scripts/tl_job.py) no manifesto ampliado por T019, sem acoplamento a uma contagem fixa (hardcoded) do total de arquivos do pacote.

### Rollout e compatibilidade opt-in
1. Projetos v0.8.0 mantendo classification_schema_version: 2 (ou ausente) permanecem 100% no pipeline legado, sem qualquer alteração comportamental.
2. A adoção de T019 é opt-in, ativada explicitamente no projeto via classification_schema_version: 3 em _tl-orc/PROJECT.md.
3. O validador oficial scripts/validate_classification.py é único e seleciona a gramática apropriada com base no campo schema_version do JSON de resultado.
