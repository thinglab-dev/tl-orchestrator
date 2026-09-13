id: T017
type: gov
deliverable: none
standalone: true
method: native
status: done
state_revision: 2
depends_on: [T016]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-12 (formalização do papel Advisor / Cross-Family Advisory)
decisions: []
spec_author: orchestrator
spec_revision: aecdc421b466be82
rework_round: 1
affects_context: []
content_paths: [distribution-manifest.json, README.md, SKILL.md, docs/PROJECT_CONFIGURATION.md, docs/WORK_MODEL.md, prompts/orchestrator.md, prompts/orchestrator-playbook.md, prompts/orchestrator-perfis.md, prompts/classifier.md, prompts/advisor.md, schemas/advisor-result.schema.json, schemas/classification-result.schema.json, scripts/tests/test_advisor_policy.py, CHANGELOG.md]
content_id: 219fa2a96d4982b184a44c8cb43f86cfdb45ed39:b4f03d754ee7588d

## Finding
source: alinhamento estratégico com o mantenedor em 2026-09-12 e lições acumuladas nos ciclos complexos de T011–T016 (em especial os replays e preflights de T015 e a cadência de T016)
observed: o método atual conta com Planner ("Como devemos fazer?"), Maker ("Implementar a spec"), Checker ("O que foi implementado atende a spec e a prova?") e painel consultivo Debate ("Escolher entre alternativas materialmente concorrentes"). No entanto, não existe um papel consultivo focado em desafio crítico e estratégico de premissas, arquitetura, evidências, causalidade e risco antes de decisões materialmente caras ou difíceis de reverter ("Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?"). Quando o Orquestrador ou Planner formulam uma direção arriscada, a validação só ocorre tardiamente no Checker (após consumir chamadas de implementação e árvore alterada) ou por intervenção manual do usuário, gerando desperdício evitável.
expected: criar o papel formal Advisor (report-only, fresh session, cross-family preferido), ativado estritamente por gatilhos objetivos declarados, com non-triggers explícitos para evitar sobreutilização rotineira, pacote mínimo de desafio (reaproveitando a Context Economy de T015), saída estruturada (proceed|adjust|plan|debate|stop) validada por schema Draft 2020-12, regra de autoria estrita (não gera autoria de produto salvo cópia substancial para spec ou content_paths), recomendação de Debate sem auto-autorização, e interface declarativa para o Modo Automático (T018).
impact: previne chamadas desperdiçadas e reworks caros decorrentes de premissas errôneas ou arquiteturas frágeis, eleva o rigor de decisões antes de ações difíceis de reverter, e preserva a independência de Checker subsequente ao separar desafio consultivo de autoria efetiva.
hypothesis: a introdução de um papel Advisor report-only com gatilhos objetivos e non-triggers contratuais, desvinculado do fluxo rotineiro por Story, oferece desafio estratégico de alta qualidade sem inflacionar o custo operacional do método nem substituir os papéis existentes.
dedup: T010 fixou limites de condução e escalonamento; T013 tratou de esperas, liveness e lote autorizado; T014 formalizou a política global de participantes; T015 tratou de context economy e selective retrieval; T016 normatizou a cadência de verificação e portões de fronteira; T017 formaliza o papel consultivo Advisor.

## Spec
### Intent
Criar e normatizar contratualmente no tl-orchestrator o papel consultivo independente Advisor (Cross-Family Strategic Challenge and Escalation), de natureza estritamente report_only, voltado ao desafio de premissas, arquitetura, evidências, causalidade e risco antes de decisões materialmente caras ou difíceis de reverter, sem sobreposição com Planner, Checker ou Debate, e sem substituição da autoridade do usuário ou do Orquestrador.

### Scope and write paths
- distribution-manifest.json: ampliação do manifesto para 19 arquivos distribuídos, incluindo prompts/advisor.md e schemas/advisor-result.schema.json.
- README.md: atualização da contagem de arquivos para 19, inclusão dos dois novos arquivos no manifesto legível, nos blocos de exportação e nos comandos de verificação de checksums.
- SKILL.md: inclusão do contrato do Advisor na seção de contratos e no roteamento de ativação.
- docs/PROJECT_CONFIGURATION.md: parametrização de advisor_independence: preferred | required e política do Advisor, e atualização da contagem de arquivos do pacote.
- docs/WORK_MODEL.md: formalização do papel Advisor, distinção perante Planner/Checker/Debate, gatilhos objetivos, non-triggers, regime de independência, pacote de contexto mínimo (challenge packet), semântica dos 5 vereditos, regra de autoria estrita e interface declarativa para o Modo Automático.
- prompts/orchestrator.md: inclusão do papel Advisor, suas vedações (report_only: true, may_edit: false, etc.) e momento de acionamento.
- prompts/orchestrator-playbook.md: diretrizes de orquestração para avaliação de gatilhos do Advisor, preparação de challenge packet, consumo mandatório de vereditos (proceed|adjust|plan|debate|stop) e escalonamento para Debate.
- prompts/orchestrator-perfis.md: inclusão da cadeia de preferência do Advisor (advisor_independence: preferred | required, fallback para degraded_same_family).
- prompts/classifier.md: capacitação do Classificador para classificar o papel advisor em requested_roles, atribuindo tier e pares modelo/effort por harness.
- prompts/advisor.md: novo prompt de contrato do Advisor definindo sua missão ("Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?"), permissões somente leitura, formato de saída e conduta de desafio crítico.
- schemas/advisor-result.schema.json: novo schema JSON Draft 2020-12 definindo a saída estruturada do Advisor (schema_version: 1, verdict, confidence, findings, alternatives, missing_evidence, debate_required, reason).
- schemas/classification-result.schema.json: atualização da definição de roles para suportar a propriedade opcional advisor.
- scripts/tests/test_advisor_policy.py: nova suíte com testes determinísticos cobrindo validação de gatilhos, non-triggers, regras de independência, fallback degradado, propagação de autoria, validação de schema e semântica de vereditos.
- CHANGELOG.md: documentação detalhada da introdução do papel Advisor e schemas associados na distribuição.

### Acceptance criteria
AC01 (Role boundary): O Advisor é estritamente report-only e consultivo. É expressamente vedado ao Advisor editar arquivos, realizar commits, alterar status de tasks/deliverables, fechar tarefas, autorizar ações, despachar agentes, substituir o Planner ou substituir o Checker (report_only: true, may_edit: false, may_commit: false, may_change_state: false, may_close_task: false, may_authorize: false, may_dispatch_agents: false, may_replace_checker: false, may_replace_planner: false, may_recommend_debate: true).
AC02 (Distinção clara de papéis): As responsabilidades são mutuamente exclusivas e documentadas: Planner ("Como devemos fazer?"), Advisor ("Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?"), Checker ("O que foi implementado atende a spec e a prova?") e Debate ("Temos alternativas materialmente concorrentes; qual direção devemos escolher?"). O Advisor não atua como Checker antecipado nem como quarta IA obrigatória por Story.
AC03 (Objective triggers): O Advisor pode ser acionado exclusivamente quando pelo menos um dos 8 gatilhos objetivos estiver presente: (1) mudança em arquitetura, protocolo, autoridade ou contrato compartilhado; (2) decisão difícil de reverter (migração ampla, cutover, alteração estrutural); (3) experimento que fundamentará decisão do método (benchmarks, A/B de governança); (4) incerteza material em trabalho com tier heavy; (5) conclusão causal relevante a partir de evidência empírica limitada; (6) recorrência de classe de falha descoberta somente por revisão independente; (7) segundo parecer explicitamente solicitado pelo usuário; (8) antes de congelar lote automático de alto custo cujas tarefas satisfaçam algum dos critérios anteriores.
AC04 (Anti-overuse / Non-triggers): É expressamente proibido acionar o Advisor por conveniência rotineira: início de Story, término de execução de Maker, entrada em revisão, changes_requested comum de revisão, Task heavy sem incerteza material, alterações documentais/status de rotina, "seria bom ter uma segunda opinião" ou "por segurança".
AC05 (Structured result): A saída do Advisor é estritamente estruturada em JSON e validada contra schemas/advisor-result.schema.json sob o padrão Draft 2020-12, contendo schema_version: 1, verdict (proceed|adjust|plan|debate|stop), confidence (high|medium|low), findings, alternatives, missing_evidence, debate_required (boolean) e reason.
AC06 (Verdict semantics): Cada veredito possui efeito operacional mandatório para o Orquestrador: proceed (o fluxo autorizado prossegue normalmente); adjust (a direção é válida, mas há correções/restrições que exigem disposição antes do próximo despacho); plan (a questão exige planejamento formal antes de implementar); debate (recomenda painel Debate formal; não o inicia por conta própria); stop (interrompe a progressão até resolução de risco, evidência ou autoridade).
AC07 (Independence & Fresh Session): Por padrão advisor_independence: preferred, exigindo sessão limpa (fresh_session: required), com preferência por família distinta daquela que produziu o artefato, plano ou decisão desafiada (não meramente contra o Maker atual). Exemplo: plano Anthropic → Advisor preferir Google ou OpenAI; plano Google → Advisor preferir OpenAI ou Anthropic; plano OpenAI → Advisor preferir Google ou Anthropic.
AC08 (Degraded fallback e Bloqueio sob Required): Se nenhuma família alternativa estiver disponível sob preferred, o uso da mesma família é admitido como fallback degradado e deve ser formalmente registrado na evidência (advisor_independence: degraded_same_family, fallback_reason: ...). Sob configuração explícita advisor_independence: required, a indisponibilidade de família cross-family bloqueia o despacho do Advisor.
AC09 (Classifier support): O Classificador (perfil fixo Agy gemini-3.8-flash-medium medium) é capaz de classificar o papel advisor em requested_roles, dimensionando o tier da consulta e escolhendo pares de modelo/effort por harness a partir do catálogo e das evidências de roteamento, sem hardcode de modelos no Orquestrador.
AC10 (Minimal challenge packet): O Advisor recebe um pacote inicial conciso (challenge packet) aproveitando as primitivas de Context Economy de T015: artefato/decisão sob desafio, objetivo, restrições, fatos conhecidos, evidências relevantes, premissas materiais, alternativas já consideradas, limites de autoridade e a pergunta específica formulada pelo Orquestrador, com retrieval adicional sob demanda via ferramentas de leitura.
AC11 (Authorship propagation): O parecer do Advisor é estritamente consultivo e NÃO insere a família do Advisor em effective_authors. Somente se conteúdo substancial (arquitetura, texto de especificação ou código de solução) produzido pelo Advisor for diretamente copiado ou incorporado à spec ou aos content_paths da entrega, a família do Advisor passa a integrar effective_authors para fins de independência do Checker subsequente.
AC12 (Debate escalation): O Advisor pode recomendar a abertura de Debate e marcar debate_required: true, mas não possui autoridade para autorizar ou iniciar o modo Debate. O início do Debate continua exigindo autorização explícita do usuário ou autorização prévia vigente.
AC13 (Blocking disposition): As recomendações adjust, plan, debate e stop, bem como debate_required: true, não podem ser ignoradas silenciosamente pelo Orquestrador antes da próxima ação material de planejamento ou implementação.
AC14 (Automatic Mode interface): A política define uma interface declarativa para consumo futuro no Modo Automático (T018), admitindo declaração de advisor_policy no lote (com habilitação, gatilhos permitidos e contabilidade de chamadas contra o orçamento congelado do lote), vedando a invocação de Advisors espontâneos fora do orçamento autorizado.
AC15 (Deterministic contractual tests): Criação de suíte de testes determinísticos em scripts/tests/test_advisor_policy.py validando os 8 gatilhos objetivos, a rejeição dos non-triggers, a resolução de independência e fallback degradado, a não-propagação e propagação condicional de autoria, a validação do schema do parecer e a semântica operacional dos cinco vereditos.

### Verification profile
gov / feat: execução da suíte contratual determinística scripts/tests/test_advisor_policy.py (exit 0), python3 scripts/validate_repository.py (exit 0, cobrindo links, packaging, contagem de 19 arquivos e integridade de schemas), git diff --check (exit 0) e auditoria de Checker independente (família elegível conforme autoria).

### Condições para promover a ready
1. ✅ Finding, Intent, Scope, os 15 ACs e Verification profile aprovados pelo mantenedor em 2026-09-12.
2. ✅ T016 (Verification Cadence) concluída e integrada em main (done).
3. ➖ Implementação (Classifier -> Maker): autorizada pelo mantenedor após formalização.

## Result
Implementação e retrabalho concluídos com sucesso no commit `15c031a49a9b4f5b160e64f8b625683290c1604f` abrangendo os 14 `content_paths`:
1. `distribution-manifest.json`: manifesto atualizado para 19 arquivos com a inclusão de `prompts/advisor.md` e `schemas/advisor-result.schema.json`.
2. `README.md`: listas canônicas sincronizadas, contagens atualizadas para 19 arquivos e blocos shell de exportação e checksum adaptados.
3. `SKILL.md`: inclusão do contrato do papel Advisor na seção de contratos e no roteamento de ativação.
4. `docs/PROJECT_CONFIGURATION.md`: parametrização de `advisor_independence: preferred | required` e interface declarativa `advisor_policy`.
5. `docs/WORK_MODEL.md`: formalização completa do papel Advisor (role boundary, distinção de papéis, 8 gatilhos objetivos, non-triggers, resolução de contra-família contra o conjunto completo de famílias autoras materiais, semântica dos 5 vereditos, disposição bloqueante, autoria estrita e interface com Modo Automático).
6. `prompts/orchestrator.md`: incorporação do papel Advisor e suas diretrizes operacionais report-only.
7. `prompts/orchestrator-playbook.md`: seção de condução do Advisor, challenge packet e tratamento mandatório de vereditos.
8. `prompts/orchestrator-perfis.md`: cadeia de preferência do Advisor e resolução contra-família para autores individuais, pares e triplet.
9. `prompts/classifier.md`: suporte ao papel `advisor` em `requested_roles` e dimensionamento de tier.
10. `prompts/advisor.md`: novo prompt de sistema com contrato normativo estrito do papel Advisor.
11. `schemas/advisor-result.schema.json`: novo schema Draft 2020-12 estrito com regra condicional `verdict == "debate" => debate_required: true`.
12. `schemas/classification-result.schema.json`: inclusão da propriedade opcional `advisor` em `properties.roles.properties`.
13. `scripts/tests/test_advisor_policy.py`: nova suíte com 41 testes determinísticos e contrafactuais cobrindo AC01–AC15 e os casos de R1 e R2.
14. `CHANGELOG.md`: documentação completa das adições e correções de r02 sob `[Unreleased]`.

## Evidence
- Arquivo de evidência consolidado: [_tl-orc/project/evidence/T017-r02.md](file:///Users/albertiano/thinglab/tl-orchestrator/_tl-orc/project/evidence/T017-r02.md).
- Target commit: `15c031a49a9b4f5b160e64f8b625683290c1604f`.
- Base commit: `219fa2a96d4982b184a44c8cb43f86cfdb45ed39`.
- Content ID canônico: `219fa2a96d4982b184a44c8cb43f86cfdb45ed39:b4f03d754ee7588d`.
- Prova direcionada: `python3 -B -m unittest scripts/tests/test_advisor_policy.py` (41/41 testes, exit 0).
- Portão canônico completo de integração (`canonical_full_gate`): `python3 scripts/validate_repository.py` na raiz (exit 0, 19 package files validados).
- Consumo orçamentário: 8 chamadas a modelos (2 Classifiers de impl/rework, 2 Makers impl/rework, 2 Classifiers de review, 2 Checkers independentes).

## Review
- Artefatos de revisão: [_tl-orc/project/evidence/T017-r02/review/](file:///Users/albertiano/thinglab/tl-orchestrator/_tl-orc/project/evidence/T017-r02/review/).
- Checker independente: OpenAI Codex `gpt-5.6-terra/high`, fresh session, report-only.
- Independência: `product_checker_independence: full_cross_family` (Maker Google Gemini 3.8 Flash High vs. Checker OpenAI Codex Terra High).
- Parecer estruturado final (r02): `approved` (0 action items, 0 deferred, 13 hipóteses rejeitadas confirmando resolução integral de R1 e R2 e não-regressão das propriedades normativas).
