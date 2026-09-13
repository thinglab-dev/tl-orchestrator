# Parecer do Checker — Story 6.0a (rodada 1)

## Parecer (objeto extraído)

```json
{
  "schema_version": 1,
  "verdict": "changes_requested",
  "action_items": [
    {
      "id": "R1",
      "severity": "medium",
      "category": "patch",
      "target_role": "maker",
      "location": "cmd/lynvia/internal/process/config.go: validateListenAddr",
      "problem": "A validação heurística `host == \"\" && port == \"8080\"` inventa uma semântica que altera o comportamento do perfil legado Bling, violando o AC01 (que exige manutenção do comportamento atual). O AC04 proíbe inicialização implícita em endereço default, mas o uso explícito de `:8080` na configuração não deve ser bloqueado artificialmente.",
      "evidence": "O Orquestrador registrou que `0.0.0.0:8080` é aceito, enquanto `:8080` é recusado com a mensagem 'endereço webhookd usa default de produção'. Essa restrição afeta quem já configurava `:8080` no perfil legado.",
      "required_action": "Remover a regra arbitrária que recusa `host == \"\" && port == \"8080\"` para preservar o comportamento do perfil Bling, mantendo a proteção contra endereços implícitos através da validação sintática com `net.SplitHostPort` e da exigência de configuração preexistente."
    }
  ],
  "deferred": [
    {
      "summary": "Validação de material público/privado ausente no perfil mkauth-control-plane",
      "evidence": "O Orquestrador notou que o KeyFile não é validado/exigido para o perfil mkauth. O AC04 pede validação 'por função'; como os handlers só serão ligados nas stories 6.0b-d (AC02), é aceitável que essa validação de material ainda não ocorra nesta fatia da entrega.",
      "location": "cmd/lynvia/internal/process/config.go: normalizeConfig",
      "severity": "low"
    },
    {
      "summary": "Falha isolada e preexistente em internal/connectorgate alheia à story",
      "evidence": "O Orquestrador reportou que o 'make check' já reprovava exclusivamente em 'internal/connectorgate' devido a uma expectativa desatualizada do oráculo de testes, tratando-se de um problema externo ao escopo modificado por esta story.",
      "location": "internal/connectorgate",
      "severity": "low"
    }
  ],
  "rejected": []
}
```

## Envelope original

```json
{
 "conversation_id": "28ab4a9e-ee0f-4e3a-9e72-df1c2427e038",
 "status": "SUCCESS",
 "response": "{\"schema_version\": 1, \"verdict\": \"changes_requested\", \"action_items\": [{\"id\": \"R1\", \"severity\": \"medium\", \"category\": \"patch\", \"target_role\": \"maker\", \"location\": \"cmd/lynvia/internal/process/config.go: validateListenAddr\", \"problem\": \"A validação heurística `host == \\\"\\\" && port == \\\"8080\\\"` inventa uma semântica que altera o comportamento do perfil legado Bling, violando o AC01 (que exige manutenção do comportamento atual). O AC04 proíbe inicialização implícita em endereço default, mas o uso explícito de `:8080` na configuração não deve ser bloqueado artificialmente.\", \"evidence\": \"O Orquestrador registrou que `0.0.0.0:8080` é aceito, enquanto `:8080` é recusado com a mensagem 'endereço webhookd usa default de produção'. Essa restrição afeta quem já configurava `:8080` no perfil legado.\", \"required_action\": \"Remover a regra arbitrária que recusa `host == \\\"\\\" && port == \\\"8080\\\"` para preservar o comportamento do perfil Bling, mantendo a proteção contra endereços implícitos através da validação sintática com `net.SplitHostPort` e da exigência de configuração preexistente.\"}], \"deferred\": [{\"summary\": \"Validação de material público/privado ausente no perfil mkauth-control-plane\", \"evidence\": \"O Orquestrador notou que o KeyFile não é validado/exigido para o perfil mkauth. O AC04 pede validação 'por função'; como os handlers só serão ligados nas stories 6.0b-d (AC02), é aceitável que essa validação de material ainda não ocorra nesta fatia da entrega.\", \"location\": \"cmd/lynvia/internal/process/config.go: normalizeConfig\", \"severity\": \"low\"}, {\"summary\": \"Falha isolada e preexistente em internal/connectorgate alheia à story\", \"evidence\": \"O Orquestrador reportou que o 'make check' já reprovava exclusivamente em 'internal/connectorgate' devido a uma expectativa desatualizada do oráculo de testes, tratando-se de um problema externo ao escopo modificado por esta story.\", \"location\": \"internal/connectorgate\", \"severity\": \"low\"}], \"rejected\": []}\n",
 "duration_seconds": 25.423145,
 "num_turns": 1,
 "usage": {
  "input_tokens": 27921,
  "output_tokens": 2883,
  "thinking_tokens": 2340,
  "cache_read_tokens": 8153,
  "total_tokens": 30804
 }
}
```

# Classificações da Rodada 1

## implementation

```json
{"schema_version":2,"story_id":"6-0a-configuracao-e-lifecycle-do-control-plane","phase":"implementation","context_revision":"platform@e4bf8560+clean-2026-09-08","catalog_revision":"_tl-orc/PROJECT.md 2026-09-06 (main@1e68982)","confidence":"medium","facts":["A implementação altera o composition root, configuração condicional, invariantes de lifecycle e testes de wiring em múltiplos arquivos.","O risco principal é regressão silenciosa no perfil Bling e a prova envolve startup, shutdown, validação antecipada e ausência de listener default.","O Maker está autorizado a usar Codex gpt-5.6-terra como preferido, com Claude e Agy na cadeia de fallback."],"uncertainties":["Não há medição local pareada nem evidência econômica específica do custo total por story.","A limitação do sandbox pode impedir listeners TCP e o portão integral depende de Postgres local."],"reclassify_when":["Reclassificar para normal se o diff ficar restrito a flags de configuração sem alteração real de lifecycle ou composition root.","Reclassificar para heavy superior somente se surgirem migração, concorrência entre subsistemas, recuperação distribuída ou mudança de isolamento.","Reavaliar os candidatos se o catálogo, a autorização de modelos ou as evidências econômicas mudarem."],"roles":{"maker":{"tier":"heavy","reason":"Mudança de alto risco no composition root de produção, com configuração condicional, lifecycle de múltiplos subsistemas, invariantes de shutdown e testes de regressão do perfil Bling.","candidates":[{"harness":"codex","model":"gpt-5.6-terra","effort":"high","evidence_ids":["gpt56-coding","price-terra"],"cost_basis":"token_price_only","reason":"Preferido e autorizado para Maker; o effort high atende a leitura cruzada, refatoração de lifecycle e provas de regressão. A evidência de capacidade é forte, mas a comparação econômica usa apenas tarifa vigente."},{"harness":"claude","model":"sonnet","effort":"high","evidence_ids":["sonnet-effort","price-sonnet"],"cost_basis":"token_price_only","reason":"Fallback de família distinta com effort high para preservar capacidade em composição e lifecycle; não há medição local que comprove menor custo por story."},{"harness":"agy","model":"gemini-3.8-flash-medium","effort":"high","evidence_ids":["flash-deepswe","price-flash"],"cost_basis":"token_price_only","reason":"Fallback final autorizado; effort high compensa a criticidade da mudança e a necessidade de testes, embora não haja evidência pareada de qualidade ou custo total."}]}}}
```

Nota de validação: o terceiro candidato (agy `gemini-3.8-flash-medium` com `effort: high`) contraria a regra dos perfis (effort embutido no ID); registrado como inconsistência do fallback, não utilizado. Primeiro candidato válido e disponível: Codex `gpt-5.6-terra`/high.

## review — rodada 1

```json
{"schema_version":2,"story_id":"6-0a-configuracao-e-lifecycle-do-control-plane","phase":"review","context_revision":"platform@e4bf8560+maker-6-0a-uncommitted-2026-09-08","catalog_revision":"_tl-orc/PROJECT.md 2026-09-06 (main@1e68982)","confidence":"medium","facts":["A revisão cobre composição raiz, lifecycle, drenagem e regressões do perfil Bling em mudança de risco médio-alto.","Há achados concretos sobre validateListenAddr e sobre validação incompleta do perfil mkauth-control-plane.","A independência do Checker é obrigatória e Codex é inelegível por compartilhar a família do Maker."],"uncertainties":["O briefing não contém o diff, a spec AC01–AC04 nem o relatório completos para inspeção direta.","Não há preço ou benchmark comparável fornecido para Gemini 3.1 Pro.","A evidência econômica de Claude é apenas tarifária e não demonstra menor custo por story nem qualidade específica para esta revisão."],"reclassify_when":["O diff ou a spec revelarem impacto limitado, sem alteração efetiva de lifecycle, composição raiz ou garantias de segurança.","Forem fornecidos dados comparáveis de custo e qualidade que indiquem um candidato suficiente de menor custo esperado.","A política de independência ou a família efetiva do Maker mudar."],"roles":{"checker":{"tier":"heavy","reason":"A revisão envolve composição root de produção, invariantes de lifecycle e drenagem, compatibilidade do perfil Bling e validações que podem propagar falso verde para 6.0b–d; exige contraprovas e independência do Maker.","candidates":[{"harness":"agy","model":"gemini-3.1-pro-high","effort":"high","evidence_ids":[],"cost_basis":"unknown","reason":"Candidato preferido pela política e adequado ao risco e à necessidade de revisão independente; não há base econômica válida fornecida para comparar custo."},{"harness":"claude","model":"sonnet","effort":"high","evidence_ids":["price-sonnet"],"cost_basis":"token_price_only","reason":"Alternativa independente autorizada, com effort high compatível com a revisão de lifecycle e segurança; a base econômica é somente tarifa vigente, sem prova de custo por tarefa ou qualidade específica."},{"harness":"codex","model":null,"effort":null,"evidence_ids":[],"cost_basis":"unknown","reason":"Inelegível porque pertence à mesma família OpenAI do Maker efetivo, violando a política de independência."}]}}}
```
