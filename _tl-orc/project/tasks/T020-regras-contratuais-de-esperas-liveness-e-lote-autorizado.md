id: T020
type: fix
deliverable: none
standalone: true
method: native
status: done
state_revision: 2
depends_on: [T011]
blocked_by: []
origin: task/T011 (análise ratificada em 2026-09-11)
decisions: []
spec_author: orchestrator
spec_revision: 073029a7b89760b9
rework_round: 0
affects_context: []
content_id: b06d37e3cca2f9f4507287c3ee25e7437db47f18:9e6cc414bfa89fbb
content_paths: [prompts/orchestrator-perfis.md, prompts/orchestrator-playbook.md, docs/WORK_MODEL.md, CHANGELOG.md, _tl-orc/project/evidence/T013-contract-tests.py]

## Finding
source: análise ratificada T011 (evidências T011-r01.md e T011-r02.md) e incidentes operacionais de 2026-09-07 (T005/T009/T010) e 2026-09-10 (bloqueio de stdin no Classificador)
observed: (1) ausência de parametrização da verificação de liveness levou a tratar processo aguardando stdin/EOF como lentidão de modelo; (2) falta de distinção de causas levou à premissa errônea de acionar fallback de IA diante de travamento de linha de comando; (3) contagem de prazo de espera humana foi cogitada sem evento comprovável de emissão; (4) a fila sequencial vigente do playbook veda avanço automático multitarefas e proíbe saltar bloqueios, mas não previa o avanço seguro sobre lotes explicitamente autorizados pelo usuário; (5) risco de agentes subordinados serem confundidos com autoridade para conceder autorizações de escopo ou orçamento.
expected: consolidar nos contratos distribuídos (`prompts/orchestrator-perfis.md`, `prompts/orchestrator-playbook.md`, `docs/WORK_MODEL.md`) as regras ratificadas em T011 r02: liveness configurável (`liveness_probe_after`), investigação mecânica agnóstica ao SO antes de inferir latência, marco `question_emitted_at`, proibição de presumir leitura humana, trava anti-salto com parada padrão na unidade bloqueada, avanço em ramos independentes condicionado a `continue_independent_on_block: true` e autoridade estritamente privativa do usuário com Debater puramente instrutivo.
impact: previne paradas redundantes em lotes autorizados, impede saltos arbitrários de tarefas bloqueadas, bloqueia fallbacks indevidos de modelos por falhas de I/O local e garante integridade jurídica da autoridade humana.
hypothesis: a incorporação direta das minutas ratificadas em T011 r02 nos três documentos distribuídos, com suporte de testes contratuais em evidência e registro no CHANGELOG, resolve as ambiguidades operacionais sem quebrar o manifesto de 17 arquivos.
next verification: implementação das alterações textuais, execução da suíte `T013-contract-tests.py`, sondas contrafactuais e revisão por Checker independente de família distinta.
dedup: T010 tratou de escalonamento após N reworks e confinamento de leitura; T011 formalizou a análise conceitual; T013 é a implementação contratual definitiva.

## Spec
### Intent
Implementar no pacote distribuído as regras contratuais ratificadas na análise T011 (r02): parametrização da sonda de liveness (`liveness_probe_after`) com investigação mecânica de I/O agnóstica ao SO antes de qualquer inferência de latência; início da contagem de prazo humano estritamente no evento tecnicamente observável `question_emitted_at` (com `transport_ack_at` se comprovado pelo canal) e vedação absoluta de presunção cognitiva; distinção rígida entre instrução por agentes (modo Debater) e autoridade de autorização (privativa do usuário); e consolidação da fila sequencial para lotes autorizados, fixando a parada imediata na primeira unidade bloqueada como regra padrão (trava anti-salto) e permitindo avanço em tarefas independentes exclusivamente sob autorização explícita (`continue_independent_on_block: true`).

### Scope and write paths
Somente: `prompts/orchestrator-perfis.md`, `prompts/orchestrator-playbook.md`, `docs/WORK_MODEL.md`, `CHANGELOG.md` (Unreleased) e a suíte de testes contratuais em `_tl-orc/project/evidence/T013-contract-tests.py`. Proibido alterar schemas, manifesto de distribuição, SKILL.md ou outros arquivos do pacote.

### Acceptance criteria
AC01 Investigação mecânica e sonda de liveness em `prompts/orchestrator-perfis.md`:
  - Inserir na subseção de Fallback e Interrupção a diretriz de que, diante de ausência de saída após limiar configurável (`liveness_probe_after`), o Orquestrador realiza investigação mecânica proporcional do subprocesso (inspecionando estado do processo, CPU, streams e descritores/pipes de I/O, garantindo que `stdin` foi fechado com EOF / `< /dev/null` e não há espera de leitura local) antes de qualquer inferência de latência de agente ou de timeout.
  - Definir que comandos como `ps`, `lsof`, APIs de SO ou cmdlets de plataforma constituem meros adaptadores de sistema operacional.
  - Fixar que falhas mecânicas simples devem ser corrigidas localmente pelo Orquestrador nos limites da autorização vigente e registradas na contabilidade de esforço da amostra do ciclo.
  - Reafirmar que timeout isolado, saída vazia ou falha repetida de invocação não autorizam fallback de modelo ou família sem comprovação inequívoca e independente de indisponibilidade da infraestrutura.

AC02 Limites de autonomia, marco temporal humano e consulta pós-prazo em `prompts/orchestrator-perfis.md`:
  - Formalizar que escolhas técnicas rotineiras delegadas na spec da Task ou no lote são exercidas diretamente pelo Orquestrador, sem paradas para confirmações triviais.
  - Fixar que perguntas submetidas ao usuário iniciam contagem de prazo estritamente no evento tecnicamente observável `question_emitted_at` (exit code 0 / retorno bem-sucedido da emissão pelo runtime).
  - Admitir `transport_ack_at` apenas quando a infraestrutura de transporte expuser confirmação efetiva de recebimento no cliente.
  - Proibir terminantemente presumir leitura, compreensão ou recepção cognitiva humana.
  - Condicionar o despacho de consulta classificada pós-prazo à presença de autorização explícita no lote (`auto_consult_after`, `max_calls`); na omissão, a execução permanece pausada aguardando resposta humana.

AC03 Papel de agentes vs autoridade do usuário em `prompts/orchestrator-perfis.md`:
  - Consolidar a regra de que agentes subordinados atuam instruindo e analisando alternativas, prós e contras (modo Debater), mas nunca possuem autoridade para conceder autorização em nome do usuário.
  - Estabelecer a vedação absoluta de agentes deliberarem sobre escopo, expansão de orçamento ou ações externas restritas.

AC04 Fila sequencial de lote autorizado em `prompts/orchestrator-playbook.md`:
  - Na subseção de Fila sequencial de stories, introduzir a diretriz de execução sobre Lote Autorizado: sob lista e escopo expressamente autorizados pelo usuário, a transição entre unidades concluídas e a próxima elegível desbloqueada na ordem topológica de dependências (`depends_on`) é contínua e automática, sem interrupção para novos menus.
  - Trava anti-salto mandatória como comportamento padrão: diante de qualquer bloqueio (falha de precondição, pendência de autorização externa, reprovação), a execução **para imediatamente na unidade bloqueada, sendo terminantemente proibido saltá-la**.
  - Cláusula de avanço independente restrita: a continuação automática restrita a tarefas topologicamente independentes (sem dependência causal com a unidade bloqueada) **só é admitida se o lote tiver autorizado explicitamente essa política** (ex.: `continue_independent_on_block: true`). Na omissão dessa declaração explícita, o lote inteiro suspende a execução na primeira unidade bloqueada.

AC05 Harmonização da Fila sequencial Native em `docs/WORK_MODEL.md`:
  - Atualizar a subseção de Fila sequencial no perfil Native para espelhar as mesmas regras de lote autorizado, parada padrão obrigatória na primeira unidade bloqueada sem salto arbitrário, cláusula explícita `continue_independent_on_block: true` para ramos independentes e cômputo temporal atrelado a `question_emitted_at`.

AC06 Testes contratuais automatizados e sondas contrafactuais:
  - Implementar script determinístico `_tl-orc/project/evidence/T013-contract-tests.py` contendo asserções automatizadas que verificam a presença e coerência das 9 regras ratificadas nos três documentos normativos (`prompts/orchestrator-perfis.md`, `prompts/orchestrator-playbook.md`, `docs/WORK_MODEL.md`).
  - Incluir sondas contrafactuais por leitura/execução comprovando: (a) processo sem saída sem investigação mecânica não pode acionar fallback; (b) ausência de `continue_independent_on_block: true` suspende a fila diante de bloqueio; (c) prazo humano computado antes de `question_emitted_at` é rejeitado; (d) agente em modo Debater tentando aprovar escopo é rejeitado como inválido.

AC07 Registro no CHANGELOG:
  - Registrar em `CHANGELOG.md` sob `## [Unreleased]` (seção `### Adicionado` e `### Alterado`) as diretrizes de condução de lote autorizado, trava anti-salto, liveness configurável e marco temporal observável.

AC08 Portão estrutural:
  - `python3 scripts/validate_repository.py` exit 0 (17 arquivos de pacote validados, links íntegros, manifestos e exports consistentes).

### Verification profile
`fix`: conferência mecânica via `_tl-orc/project/evidence/T013-contract-tests.py`, sondas contrafactuais por leitura (AC06), validador estrutural do repositório exit 0 e Checker independente de família distinta em sessão nova.

## Result
Implementação concluída com fidelidade normativa estrita às minutas ratificadas em T011 r02, cobrindo os critérios AC01 a AC08:
1. `prompts/orchestrator-perfis.md`: incorporação do parâmetro configurável `liveness_probe_after`, investigação mecânica proporcional antes de inferência de latência, verificação agnóstica de processo e descritores/pipes de I/O com garantia de EOF/`< /dev/null`, adaptação via `ps`/`lsof`, reparo mecânico local com esforço contabilizado, proibição de fallback sem prova inequívoca de indisponibilidade, cômputo de prazo humano atrelado a `question_emitted_at` com proibição de presunção cognitiva, consulta pós-prazo sob cláusula explícita, e restrição de autoridade a usuários com agentes restritos a instrução (modo Debater).
2. `prompts/orchestrator-playbook.md`: fila sequencial de Lote Autorizado com avanço contínuo e automático na ordem topológica de dependências (`depends_on`), trava anti-salto como regra padrão mandatória (parada imediata na unidade bloqueada sem salto arbitrário) e continuação em tarefas independentes estritamente sob `continue_independent_on_block: true`.
3. `docs/WORK_MODEL.md`: subseção Native harmonizada com avanço sobre lote autorizado, trava anti-salto padrão, autorização explícita de continuação independente e evento `question_emitted_at`.
4. `CHANGELOG.md`: registros documentados sob `## [Unreleased]`.
5. `_tl-orc/project/evidence/T013-contract-tests.py`: suíte determinística com asserções das 9 regras e 4 simuladores contrafactuais executáveis (trava anti-salto, liveness guard, timeout humano, autoridade de agente).
6. Portão estrutural: `python3 scripts/validate_repository.py` exit 0 (17 arquivos de pacote íntegros).
7. Prova de conformidade: `python3 _tl-orc/project/evidence/T013-contract-tests.py` exit 0.

## Evidence
`_tl-orc/project/evidence/T013-r01.md`, `_tl-orc/project/evidence/T013-contract-tests.py`.

## Review
Rodada r01 realizada com estrita conformidade à regra `checker_independence: required`: autoria do Orquestrador sob harness Antigravity (família Google) -> Checker independente da família Anthropic (Claude `sonnet`, esforço `high`, sessão isolada confinado a `Read,Glob,Grep`). Veredito `approved` (0 `action_items`, 3 `deferred` de severidade low documentando conformidade e notas de especificidade de teste/espelho, 0 `rejected`), validado com sucesso pelo validador JSON Schema Draft 2020-12 (AJV 2020). Orçamento consumido: exatamente 2 chamadas a modelos (1 Classificador + 1 Checker independente), dentro do limite estrito da Opção 1 autorizada. Transição para `done` com `state_revision: 2`.
