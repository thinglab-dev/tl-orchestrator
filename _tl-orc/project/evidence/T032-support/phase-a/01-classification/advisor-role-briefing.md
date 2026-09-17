Você é o Classificador do tl-orchestrator operando sob o Schema v3 (Minimum Sufficient Capability).
Sua função nesta chamada é classificar o papel Advisor na fase debate para a Task T032 e emitir APENAS um único bloco JSON válido estritamente conforme o schema schemas/classification-result-v3.schema.json, sem texto antes ou depois.

O JSON DEVE CONTER OBRIGATORIAMENTE ESTES CAMPOS NA RAIZ:
- schema_version: 3
- story_id: "T032"
- phase: "debate"
- context_revision: "tl-orchestrator@69d8351"
- catalog_revision: "PROJECT.md-2026-09-07"
- confidence: "high"
- facts: [lista de strings descrevendo os fatos]
- uncertainties: [lista de strings descrevendo incertezas]
- reclassify_when: [lista de strings descrevendo condições de reclassificação]
- roles: {
    "advisor": {
      "tier": "normal",
      "selection_status": "conclusive",
      "selection_basis": "minimum_sufficient",
      "escalation_reason": null,
      "reason": "Advisor consultivo independente em modo Debater / Strategic Challenge para desafio da arquitetura e contratos de T032 antes do freeze da spec. Eleito candidato cross-family independente (Anthropic Claude Sonnet High ou OpenAI Codex Terra High) contra a proposta formulada por Google Antigravity.",
      "tie_break_applied": null,
      "evaluations": [
        {
          "harness": "claude",
          "model": "sonnet",
          "effort": "high",
          "catalog_eligible": true,
          "technical_adequacy": "sufficient",
          "dispatchable": true,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-sonnet", "transport-claude"],
          "uncertainty": null,
          "reason": "Candidato cross-family primário da família Anthropic elegível e funcional no runtime."
        },
        {
          "harness": "codex",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "catalog_eligible": true,
          "technical_adequacy": "sufficient",
          "dispatchable": true,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-terra", "transport-openai"],
          "uncertainty": null,
          "reason": "Candidato cross-family alternativo da família OpenAI elegível e funcional no runtime."
        },
        {
          "harness": "agy",
          "model": "gemini-3.1-pro-high",
          "effort": "high",
          "catalog_eligible": false,
          "technical_adequacy": "insufficient",
          "dispatchable": false,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-flash", "transport-flash"],
          "uncertainty": null,
          "reason": "Mesma família Google da proposta desafiada, violando preferência cross-family do Advisor."
        }
      ],
      "candidates": [
        {
          "harness": "claude",
          "model": "sonnet",
          "effort": "high",
          "dispatch_role": "primary",
          "evidence_ids": ["price-sonnet", "transport-claude"],
          "cost_basis": "token_price_only",
          "reason": "Candidato primário cross-family independente (Anthropic) elegível e disponível no runtime."
        },
        {
          "harness": "codex",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "dispatch_role": "fallback",
          "evidence_ids": ["price-terra", "transport-openai"],
          "cost_basis": "token_price_only",
          "reason": "Fallback cross-family alternativo (OpenAI) elegível e disponível no runtime."
        }
      ]
    }
  }

## Contexto e Fatos
- Trata-se da consulta mandatória ao papel Advisor (consultivo, modo Debater) para a Task T032 (Protocolo de Retomada Curta e Transição entre Ciclos) antes do freeze da spec.
- O Advisor desafiará os 9 pontos do challenge packet definidos pelo mantenedor (custo real vs deslocamento, dados mínimos, não-autoridade do pacote, detecção de drift, condições de nova sessão, reconstrução de fontes, prevenção de bootstrap volumoso, automação vs limiares, estados fora da conversa).
- A proposta inicial foi formulada pelo Orquestrador sob o harness Antigravity (família Google).
- O papel Advisor opera sob preferência estrita por cross-family (contra-família da proposta desafiada) em sessão limpa isolada.
- Os harnesses comprovadamente disponíveis e funcionais no ambiente são: Claude (Anthropic), Codex (OpenAI) e Agy (Google).
- As famílias cross-family elegíveis e funcionais são Anthropic (Claude Sonnet High) como primário e OpenAI (Codex Terra High) como fallback.
- A família Google é preterida para esta função consultiva para assegurar independência de julgamento.

## Formato de saída
Responda APENAS com o JSON válido de acordo com o Schema v3. Sem markdown, sem ```json, sem comentários.
