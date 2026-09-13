Você é o Checker independente do tl-orchestrator, operando sob o contrato prompts/checker-report-only.md (leia-o e respeite-o estritamente).
Você está em uma sessão nova, somente leitura, avaliando o repositório em /Users/albertiano/thinglab/tl-orchestrator.
NÃO modifique nenhum arquivo. Responda exclusivamente com um objeto JSON válido conforme schemas/review-result.schema.json (schema_version: 1), sem texto antes ou depois, sem markdown fences.

## Metadados Canônicos da Entrega
- story_id: "T017"
- phase: review
- target_commit: eadf2ad35ee21e7b1a5a96fa992f36047ad45c63
- base_commit: 219fa2a96d4982b184a44c8cb43f86cfdb45ed39
- spec_revision: aecdc421b466be82
- content_id: 219fa2a96d4982b184a44c8cb43f86cfdb45ed39:d7addc57dc2e5189
- effective_authors: [google] (Maker foi Agy gemini-3.8-flash-high; Checker OpenAI Codex atua com independência cross-family total)
- verification_scope: targeted
- integration_group:
    authority: native_standalone
    id: T017
- canonical_full_gate:
    required_now: false
    required_at_group_boundary: true

## Razão explícita de o Full Integration Gate não ter sido executado nesta fase
A ausência de full integration gate nesta fase é intencional, mandatória e estritamente conforme a política de cadência de verificação introduzida por T016:
> **"targeted early and throughout → canonical full integration gate only at major boundary"**

Sob `verification_scope: targeted`, a exigência probatória limita-se à verificação direcionada (diff, consumidores diretos, ACs específicos e testes contratuais). O portão completo canônico de integração (`canonical_full_gate`) pertence à fronteira do grupo e será disparado uma única vez após o parecer aprovado, imediatamente antes de fechar o integration group T017 e transicionar para T018. Conforme instrução mandatória em `prompts/checker-report-only.md`, a ausência de execução prévia do full gate rotineiro nesta etapa NÃO constitui deficiência probatória, omissão ou motivo de changes_requested.

## Escopo sob Revisão (exatamente 14 content_paths, +1247 / -32 linhas entre base_commit e target_commit)
1. `distribution-manifest.json` (ampliado para 19 arquivos canônicos)
2. `README.md` (atualizado para 19 arquivos, manifesto legível, blocos de exportação e checksums)
3. `SKILL.md` (contrato do Advisor em Contratos e roteamento normativo)
4. `docs/PROJECT_CONFIGURATION.md` (19 arquivos, política advisor_independence e interface advisor_policy)
5. `docs/WORK_MODEL.md` (seção normativa integral do papel Advisor)
6. `prompts/orchestrator.md` (inclusão do papel Advisor, restrições report-only e triggers)
7. `prompts/orchestrator-playbook.md` (seção Condução do Advisor, challenge packet, disposição de vereditos)
8. `prompts/orchestrator-perfis.md` (cadeia de preferência do Advisor, contra-família e fallback)
9. `prompts/classifier.md` (suporte ao papel advisor em requested_roles)
10. `prompts/advisor.md` (novo prompt de contrato normativo do Advisor)
11. `schemas/advisor-result.schema.json` (novo schema Draft 2020-12 do parecer do Advisor)
12. `schemas/classification-result.schema.json` (suporte a propriedade opcional advisor em roles)
13. `scripts/tests/test_advisor_policy.py` (nova suíte com 33 testes determinísticos e contrafactuais)
14. `CHANGELOG.md` (registro detalhado sob [Unreleased] -> Adicionado)

## Provas Existentes Coletadas pelo Maker
1. `python3 -B -m unittest scripts/tests/test_advisor_policy.py` -> Exit 0, 33 testes em 0.002s, 100% verde (OK).
2. `python3 -B -m unittest scripts/tests/test_verification_cadence.py` -> Exit 0, 25 testes em 0.000s, 100% verde (OK).
3. `python3 scripts/validate_repository.py` -> Exit 0 (19 package files; JSON, frontmatter, links, export e hashes validados).
4. `git diff --check` -> Exit 0 (zero whitespace problemático ou conflito).

## Critérios de Aceitação da Spec (AC01–AC15)
- AC01 (Role boundary): Advisor é estritamente report-only (`may_edit: false`, `may_commit: false`, `may_change_state: false`, `may_close_task: false`, `may_authorize: false`, `may_dispatch_agents: false`, `may_replace_checker: false`, `may_replace_planner: false`, `may_recommend_debate: true`).
- AC02 (Distinção de papéis): Planner ("Como devemos fazer?"), Advisor ("Isso que pretendemos fazer faz sentido? Que premissa pode estar errada?"), Checker ("O que foi implementado atende a spec e a prova?") e Debate ("Temos alternativas materialmente concorrentes; qual direção devemos escolher?") com responsabilidades não sobrepostas. Advisor não é Checker antecipado nem 4ª IA obrigatória.
- AC03 (Objective triggers): Acionamento restrito a pelo menos 1 dos 8 gatilhos objetivos declarados.
- AC04 (Anti-overuse / Non-triggers): Proibido acionar Advisor por conveniência rotineira (início de Story, término de Maker, review, changes_requested normal, heavy sem incerteza material, alterações documentais/status, "segunda opinião", "por segurança").
- AC05 (Structured result): Saída do Advisor estritamente em JSON validada contra `schemas/advisor-result.schema.json` (Draft 2020-12).
- AC06 (Verdict semantics): Semântica mandante dos 5 vereditos (`proceed`, `adjust`, `plan`, `debate`, `stop`).
- AC07 (Independence & Fresh Session): Padrão `advisor_independence: preferred`, `fresh_session: required`, avaliada contra a família do artefato/decisão sob desafio (contra-família).
- AC08 (Degraded fallback vs Required): Fallback same-family admitido sob `preferred` apenas como `degraded_same_family` com registro obrigatório; sob `required`, indisponibilidade cross-family bloqueia o despacho.
- AC09 (Classifier support): Classificador dimensiona tier (`normal` ou `heavy`) e escolhe modelo/effort por harness sem hardcode no Orquestrador.
- AC10 (Minimal challenge packet): Pacote de desafio enxuto sob Context Economy (T015) com consultas seletivas sob demanda.
- AC11 (Authorship propagation): Parecer do Advisor NÃO entra em `effective_authors`, exceto se conteúdo substancial (arquitetura, spec, código) for diretamente incorporado à entrega.
- AC12 (Debate escalation): Advisor pode recomendar Debate (`debate_required: true`), mas nunca o autoriza ou inicia por conta própria.
- AC13 (Blocking disposition): Recomendações `adjust`, `plan`, `debate`, `stop` e `debate_required: true` não podem ser ignoradas silenciosamente antes da próxima ação material.
- AC14 (Automatic Mode interface): Interface declarativa para `advisor_policy` no lote (T018) com contabilidade de orçamento, sem Advisors espontâneos fora do lote.
- AC15 (Deterministic contractual tests): Suíte determinística em `scripts/tests/test_advisor_policy.py` cobrindo integralmente AC01–AC15.

## Sondas e Investigações Críticas Obrigatórias para a Revisão
Audite o diff e tente quebrar especificamente estas 9 propriedades fundamentais:
1. **Advisor não vira Checker antecipado nem Planner paralelo:** Os prompts e documentos garantem que o Advisor critique premissas e riscos antes da ação, sem auditar diffs de código implementado nem produzir especificações completas de tarefas?
2. **`heavy` sozinho não dispara Advisor:** Está contratualmente vedado chamar o Advisor apenas porque a tarefa é tier `heavy`, exigindo comprovação de incerteza material ou risco arquitetural?
3. **Fallback degradado vs Bloqueio sob Required:** Sob `preferred`, o uso de mesma família gera obrigatoriamente a marcação `degraded_same_family` e justificativa? E sob `required`, a indisponibilidade cross-family comprovadamente impede o despacho?
4. **Propagação condicional de autoria:** A autoria do Advisor fica isolada da do produto, entrando em `effective_authors` estritamente se houver incorporação material à spec ou código?
5. **Disposição obrigatória de vereditos restritivos:** O Orquestrador é impedido de seguir adiante silenciosamente após receber `adjust`, `plan`, `debate` ou `stop`?
6. **Debate sem auto-autorização:** A indicação `debate_required: true` permanece estritamente como recomendação, mantendo a necessidade de autorização humana ou prévia vigente?
7. **Isolamento de T018:** A interface declarativa `advisor_policy` foi introduzida sem implementar o Modo Automático antecipadamente dentro de T017?
8. **Compatibilidade de schema no Classifier:** O schema `classification-result.schema.json` e o contrato do Classificador aceitam legitimamente `requested_roles: ["advisor"]` sem conflito com os outros papéis?
9. **Sonda de múltiplos autores:** Se o artefato desafiado tiver múltiplos autores (ex.: `effective_authors: [google, openai]`), a política do Advisor exige preferência por Anthropic, sem se limitar a comparar contra o "último Maker"?

## Instruções para o Parecer JSON
- Examine o diff real entre base_commit e target_commit e os arquivos na árvore.
- Em `action_items`: liste apenas ações obrigatórias não resolvidas para esta entrega (se houver, verdict deve ser `changes_requested`). Se todos os ACs estiverem satisfeitos e as 9 sondas refutadas sem defeitos bloqueantes, `action_items` deve ser `[]` e verdict deve ser `approved`.
- Em `rejected`: registre formalmente as hipóteses investigadas e refutadas (especialmente as 9 investigações críticas e os ACs).
- Em `deferred`: registre observações informativas ou desvios secundários não bloqueantes, se houver.
- Formato: exclusivamente o objeto JSON Draft 2020-12 correspondente a schemas/review-result.schema.json, sem texto ao redor.
