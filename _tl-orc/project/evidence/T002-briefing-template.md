# Template de Briefing Mínimo do Classificador (T002)

Este artefato define o template padrão de briefing para o papel Classificador (`Codex gpt-5.6-luna`, `effort: medium`), em conformidade com o contrato em `prompts/classifier.md`, as regras de perfis e despacho em `prompts/orchestrator-perfis.md` e a tabela normativa de procedência.

---

## 1. Instruções para o Consumidor (Orquestrador)

Ao preparar o despacho do Classificador, o Orquestrador deve compor o prompt estruturado observando as seguintes regras:
1. **Geração e Preservação do Bloco de Esqueleto:** O bloco `## 3. Esqueleto JSON Obrigatório` deve ser gerado programmaticamente a partir do schema para os papéis solicitados (`requested_roles`, inclusive `searcher` quando solicitado sozinho ou com outros) e com as cadeias operacionais efetivamente configuradas para a fase/tarefa (respeitando `prompts/classifier.md:46, 104` e as configurações do projeto, ex: `_tl-orc/PROJECT.md:45-46`), utilizando o protótipo `_tl-orc/project/evidence/T002-briefing-skeleton.py` ou mecanismo equivalente do consumidor. Somente após essa geração o bloco de esqueleto e as `## 4. Regras Fixas de Preenchimento` devem ser incluídos no despacho de forma textual e preservados inalterados. Nunca substitua o esqueleto literal por explicações dos campos em prosa (nos experimentos observados, a ausência conjunta de esqueleto literal e regras fixas coincidiu com falhas estruturais sistemáticas em prosa).
2. **Preenchimento dos Placeholders:** Substitua cada placeholder `<...>` da seção de entradas com o valor concreto extraído da fonte autorizada correspondente.
3. **Procedência Obrigatória por Entrada:** Cada valor informado deve declarar explicitamente sua origem conforme a tabela de procedência de `prompts/orchestrator-perfis.md:236-244`. IDs fabricados ou entradas sem origem verificável são expressamente rejeitados.
4. **Registros Estruturados Reais para Medições Locais:** Para identificadores de medições locais (`local-*`), é obrigatório que cada ID conste na primeira coluna de uma tabela estruturada em evidência do projeto (`prompts/orchestrator-perfis.md:242-245`). Referências genéricas a arquivos ou IDs que não constem na primeira coluna são expressamente proibidos.
5. **Catálogo com Autorização e Restrições por Papel:** Cada entrada do catálogo deve explicitar para quais papéis está autorizada e as restrições aplicáveis a cada papel (`prompts/classifier.md:30`), com procedência verificável por linha.
6. **Conjunto Enviado:** Entregue o contrato (`prompts/classifier.md`), o schema compacto (`schemas/classification-result.schema.json`) e o briefing montado na mesma chamada de despacho, sem ferramentas.

---

## 2. Template de Entrada do Briefing

```markdown
# Briefing de Classificação

## Contexto e Identificação da Tarefa
- story_id: <ID literal da Task/Story, ex: "T002", "billing:T012", ou null sem story> (Fonte: <caminho_da_spec>:<linha>)
- phase: <debate|planning|implementation|review|rework> (Fonte: solicitação da fase atual)
- requested_roles: <planner,maker,checker[,searcher]> (Fonte: papéis autorizados para esta fase)
- context_revision: <hash ou string literal de revisão do contexto de trabalho>
- catalog_revision: <identificador literal da revisão do catálogo de modelos>
- contract_revision: <revisão do contrato/schema utilizado>

## Intenção, Trabalho Residual e Riscos
- Intenção: <resumo objetivo da spec congelada>
- Modo autorizado: <native|assistido|consultivo>
- Trabalho residual: <descrição do trabalho que resta executar nesta fase>
- Riscos materiais: <pontos críticos, integridade, segurança, concorrência, etc.>
- Provas existentes e faltantes: <testes já verdes vs verificações pendentes>
- Lacunas abertas: <incertezas ou decisões ainda não consolidadas>

## Políticas de Despacho, Pins e Cadeias
- Precedência de política: <instrução do usuário | PROJECT.md | perfil publicado>
- Cadeias de preferência informadas:
  - Planner: <ex: claude → codex → agy>
  - Maker: <ex: agy → codex → claude>
  - Checker: <ex: codex → claude → agy>
  - Searcher (se solicitado): <ex: agy → claude → codex>
- Pins e restrições fixadas: <ex: Maker fixado em agy/gemini-3.8-flash-high; Checker codex/gpt-6-astra/high>
- Independência do Checker: <required | preferred>
- Autoria efetiva anterior: <famílias e modelos registrados em Agent runs da unidade> (Fonte: <caminho_da_evidência>:<linha>)
- Orçamento da fase: <moderado|baixo|restrito>, max e ultra <proibidos|autorizados com justificativa>

## Catálogo Autorizado por Harness
(Fonte de política: <PROJECT.md#perfil-de-despacho ou perfil publicado em orchestrator-perfis.md:37-40>)
- Codex:
  - <modelo_1>: efforts <lista_efforts>, família <OpenAI>, capacidades <resumo>, papéis autorizados <planner,maker,checker>, restrições por papel <ex: Checker requer família distinta da autoria efetiva; pins>, procedência: <PROJECT.md:linha>
  - <modelo_2>: efforts <lista_efforts>, família <OpenAI>, capacidades <resumo>, papéis autorizados <planner,maker>, restrições por papel <ex: nenhum>, procedência: <PROJECT.md:linha>
- Claude:
  - <modelo_1>: efforts <lista_efforts>, família <Anthropic>, capacidades <resumo>, papéis autorizados <planner,maker,checker>, restrições por papel <ex: Checker requer família distinta da autoria efetiva>, procedência: <PROJECT.md:linha>
- Agy / Antigravity:
  - <modelo_1>: efforts <lista_efforts>, família <Google>, capacidades <resumo>, papéis autorizados <planner,maker,checker,searcher>, restrições por papel <ex: Maker pin prioritário>, procedência: <PROJECT.md:linha>

## Recorte Pertinente de Evidências Oficiais e Medições Locais
(Fonte oficial: docs/MODEL_ROUTING.md; fonte local: registros estruturados em evidências do projeto)
- IDs de evidência de preço / transporte (docs/MODEL_ROUTING.md:14-25):
  - `<price-ID>`: <resumo e modelo associado> (Fonte: docs/MODEL_ROUTING.md:linha)
  - `<transport-ID>`: <resumo e modelo associado> (Fonte: docs/MODEL_ROUTING.md:linha)
- IDs de evidência de capacidade / benchmark (docs/MODEL_ROUTING.md:26-36):
  - `<card-ID>`: <resumo do cartão e modelo associado> (Fonte: docs/MODEL_ROUTING.md:linha)
- IDs de medições locais comparáveis (prompts/orchestrator-perfis.md:242-245):
  - `<local-ID>`: <tarefa, papel, modelo, métrica observada> (Fonte: tabela estruturada em <caminho_evidência>:<linha>, onde <local-ID> consta obrigatoriamente na primeira coluna)
```

---

## 3. Esqueleto JSON Obrigatório

*(Exemplo ilustrativo gerado a partir de `schemas/classification-result.schema.json` via `T002-briefing-skeleton.py` para os papéis `planner`, `maker` e `checker` com cadeias padrão. No despacho real, gere o bloco previamente com os papéis e as cadeias efetivamente recebidos para a fase, inclusive o caso de `searcher` sozinho, preservando o resultado literalmente)*

```json
{
  "schema_version": 2,
  "story_id": "<story_id ou null>",
  "phase": "debate|planning|implementation|review|rework",
  "context_revision": "<context_revision literal recebida>",
  "catalog_revision": "<catalog_revision literal recebida>",
  "confidence": "high|medium|low",
  "facts": [
    "<fato 1>",
    "<fato 2>"
  ],
  "uncertainties": [
    "<incerteza 1>"
  ],
  "reclassify_when": [
    "<condição de reclassificação 1>"
  ],
  "roles": {
    "planner": {
      "tier": "simple|normal|heavy",
      "reason": "<justificativa do dimensionamento de tier para planner>",
      "candidates": [
        {
          "harness": "claude",
          "model": "<ID do modelo no catálogo para claude ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness claude>"
        },
        {
          "harness": "codex",
          "model": "<ID do modelo no catálogo para codex ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness codex>"
        },
        {
          "harness": "agy",
          "model": "<ID do modelo no catálogo para agy ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness agy>"
        }
      ]
    },
    "maker": {
      "tier": "simple|normal|heavy",
      "reason": "<justificativa do dimensionamento de tier para maker>",
      "candidates": [
        {
          "harness": "codex",
          "model": "<ID do modelo no catálogo para codex ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness codex>"
        },
        {
          "harness": "claude",
          "model": "<ID do modelo no catálogo para claude ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness claude>"
        },
        {
          "harness": "agy",
          "model": "<ID do modelo no catálogo para agy ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness agy>"
        }
      ]
    },
    "checker": {
      "tier": "simple|normal|heavy",
      "reason": "<justificativa do dimensionamento de tier para checker>",
      "candidates": [
        {
          "harness": "agy",
          "model": "<ID do modelo no catálogo para agy ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness agy>"
        },
        {
          "harness": "claude",
          "model": "<ID do modelo no catálogo para claude ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness claude>"
        },
        {
          "harness": "codex",
          "model": "<ID do modelo no catálogo para codex ou null se lacuna>",
          "effort": "none|minimal|low|medium|high|xhigh|max|ultra|null",
          "evidence_ids": [
            "<ID de evidência pertinente do MODEL_ROUTING ou medição local>"
          ],
          "cost_basis": "local_observed|official_task_proxy|token_price_only|unknown",
          "reason": "<justificativa da escolha ou da lacuna/inelegibilidade no harness codex>"
        }
      ]
    }
  }
}
```

> **Nota sobre papéis e Searcher:** O bloco acima é ilustrativo. O despacho deve conter exatamente os papéis solicitados (`prompts/classifier.md:104`) e respeitar as cadeias configuradas (`:46`). Quando o papel `searcher` for solicitado sozinho (`--roles searcher`), o esqueleto conterá unicamente a chave `"searcher"` em `"roles"` com a cadeia configurada (`agy → claude → codex`). Quando solicitado em conjunto com os demais (`--roles planner,maker,checker,searcher`), conterá todos os papéis solicitados com suas respectivas cadeias.

---

## 4. Regras Fixas de Preenchimento do Resultado

1. **Candidatos por cadeia:** Inclua exatamente um candidato por harness na ordem da cadeia informada, **inclusive candidatos inelegíveis pela política vigente** (que devem ser mantidos na cadeia com o motivo da inelegibilidade explicitado no campo `reason`).
2. **Lacuna no catálogo:** Se não houver par modelo/effort adequado e autorizado no catálogo para um determinado harness, devolva `"model": null` e `"effort": null`, com a justificativa da lacuna em `reason`.
3. **Pertinência de evidências:** O campo `evidence_ids` deve conter exclusivamente identificadores únicos presentes no briefing, pertinentes ao modelo e à tarefa avaliada.
4. **Base de custo (`cost_basis`):** Use `local_observed` para medição local fornecida; `official_task_proxy` para proxy oficial de tarefa; `token_price_only` para tarifa de token publicada; ou `unknown` quando não houver base econômica. Quando diferente de `unknown`, `evidence_ids` deve conter ao menos um ID econômico pertinente.
5. **Sem propriedades extras:** O schema impõe `additionalProperties: false` em todos os níveis. É estritamente proibido emitir propriedades não previstas no schema.
6. **Fechamento obrigatório:** Responda exclusivamente com o objeto JSON íntegro, garantindo o fechamento correto de todas as chaves e colchetes. Sem texto introdutório, sem comentários, sem dados adicionais e sem truncamento ou fechamento prematuro.
