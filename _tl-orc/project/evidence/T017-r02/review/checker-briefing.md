Você é o Checker independente do tl-orchestrator, operando sob o contrato prompts/checker-report-only.md (leia-o e respeite-o estritamente).
Você está em uma sessão nova, somente leitura, avaliando o repositório em /Users/albertiano/thinglab/tl-orchestrator.
NÃO modifique nenhum arquivo. Responda exclusivamente com um objeto JSON válido conforme schemas/review-result.schema.json (schema_version: 1), sem texto antes ou depois, sem markdown fences.

## Metadados Canônicos da Entrega (Rodada r02 após Rework)
- story_id: "T017"
- phase: review
- target_commit: 15c031a49a9b4f5b160e64f8b625683290c1604f
- base_commit: 219fa2a96d4982b184a44c8cb43f86cfdb45ed39
- spec_revision: aecdc421b466be82
- content_id: 219fa2a96d4982b184a44c8cb43f86cfdb45ed39:b4f03d754ee7588d
- effective_authors: [google] (Maker r01 e r02 foram Google Agy gemini-3.8-flash-high; Checker OpenAI Codex atua com total independência cross-family)
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

## Escopo sob Revisão (exatamente 14 content_paths entre base_commit e target_commit)
1. `distribution-manifest.json` (19 arquivos canônicos)
2. `README.md` (19 arquivos, manifesto legível, blocos shell de exportação e checksums)
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
13. `scripts/tests/test_advisor_policy.py` (suíte determinística expandida com 41 testes)
14. `CHANGELOG.md` (registro detalhado sob [Unreleased] -> Adicionado e Corrigido)

## Correções Específicas do Rework r02 a Auditar (Itens R1 e R2 de r01)

### 1. Resolução de R1 (Multi-author cross-family resolution):
- O Maker substituiu o modelo baseado em uma única família autora pelo conjunto completo `challenged_author_families`:
  $$\text{eligible\_cross\_family} = \text{famílias disponíveis} - \text{challenged\_author\_families}$$
- Regras normativas auditadas:
  * 1 autor: `[google] -> openai | anthropic`, `[openai] -> google | anthropic`, `[anthropic] -> google | openai`.
  * Pares de autores: `[google, openai] -> anthropic` (obrigatoriamente Anthropic quando disponível; não depende do último autor); `[google, anthropic] -> openai`; `[openai, anthropic] -> google`.
  * Triplet com as 3 famílias `[google, openai, anthropic]`: sob `advisor_independence: required`, bloqueia formalmente o despacho; sob `preferred`, admite fallback degradado `degraded_same_family` com `fallback_reason` obrigatório não vazio citando as famílias conflitantes.
- Verifique se a documentação em `docs/WORK_MODEL.md`, `prompts/orchestrator-perfis.md`, `prompts/orchestrator-playbook.md` e os testes em `scripts/tests/test_advisor_policy.py` implementam essa abstração de conjuntos com rigor.

### 2. Resolução de R2 (Invariante verdict=debate => debate_required=true):
- O schema `schemas/advisor-result.schema.json` agora impõe a condicional Draft 2020-12 via `allOf`: quando `verdict == "debate"`, então `debate_required` deve ser `true`.
- A regra inversa NÃO foi imposta: `verdict: "adjust"` com `debate_required: true` permanece válido.
- A suíte `scripts/tests/test_advisor_policy.py` contém testes contrafactuais explícitos para essas combinações.
- Verifique se o schema Draft 2020-12 e o prompt `prompts/advisor.md` estão íntegros e consistentes.

### 3. Não-regressão das 10 propriedades já validadas em r01:
Confirme que os 10 pontos rejeitados em r01 continuam sólidos:
1. Advisor não vira Checker antecipado nem Planner paralelo.
2. Tier heavy isolado não dispara Advisor (requer incerteza material).
3. Fallback same-family exige marcação explícita `degraded_same_family` e bloqueia sob `required`.
4. Propagação condicional de autoria (Advisor só entra em effective_authors se incorporado).
5. Vereditos restritivos (`adjust`, `plan`, `debate`, `stop`) exigem disposição obrigatória.
6. `debate_required: true` não autoriza Debate por si só.
7. `advisor_policy` em T018 é estritamente declarativa sem runtime antecipado.
8. Schema de classificação aceita `requested_roles: ["advisor"]`.
9. Distribuição e 19 package files íntegros e validados.
10. `verification_scope: targeted` válido sob a política T016.

## Provas Existentes Coletadas pelo Maker
1. `python3 -B -m unittest scripts/tests/test_advisor_policy.py` -> Exit 0, 41 testes em 0.001s, 100% verde (OK).
2. `python3 scripts/validate_repository.py` -> Exit 0 (19 package files; JSON, frontmatter, links, export e hashes validados).
3. `git diff --check` -> Exit 0 (zero whitespace problemático ou conflito).

## Instruções para o Parecer JSON
- Examine o diff real entre base_commit e target_commit e os arquivos na árvore.
- Em `action_items`: se R1 e R2 foram plenamente resolvidos e não há novas regressões, `action_items` deve ser `[]` e `verdict` deve ser `approved`. Se restar algum vício impeditivo, liste os action items e emita `changes_requested`.
- Em `rejected`: registre formalmente as hipóteses investigadas e refutadas (incluindo a resolução de R1, R2 e a não-regressão dos pontos anteriores).
- Em `deferred`: registre observações secundárias não bloqueantes, se houver.
- Formato: exclusivamente o objeto JSON Draft 2020-12 correspondente a schemas/review-result.schema.json, sem texto ao redor.
