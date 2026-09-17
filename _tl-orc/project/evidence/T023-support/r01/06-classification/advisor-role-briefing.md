Você é o Classificador do tl-orchestrator operando sob o Schema v3 (Minimum Sufficient Capability).
Sua função nesta chamada é classificar a fase indicada e emitir APENAS um único bloco JSON válido estritamente conforme o schema schemas/classification-result-v3.schema.json, sem texto antes ou depois.

O JSON DEVE CONTER OBRIGATORIAMENTE ESTES CAMPOS NA RAIZ:
- schema_version: 3
- story_id: "T023"
- phase: "debate"
- context_revision: "tl-orchestrator@3b7ff25"
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
      "reason": "Advisor consultivo em modo Debater para saneamento de protocolo experimental antes do congelamento. Eleito primário da família Google (cross-family contra proposta OpenAI).",
      "tie_break_applied": null,
      "evaluations": [
        {
          "harness": "agy",
          "model": "gemini-3.1-pro-high",
          "effort": "high",
          "catalog_eligible": true,
          "technical_adequacy": "sufficient",
          "dispatchable": true,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-flash", "transport-flash"],
          "uncertainty": null,
          "reason": "Candidato cross-family primário da família Google elegível e disponível no runtime."
        },
        {
          "harness": "claude",
          "model": "sonnet",
          "effort": "high",
          "catalog_eligible": true,
          "technical_adequacy": "sufficient",
          "dispatchable": false,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-sonnet", "transport-claude"],
          "uncertainty": null,
          "reason": "Indisponível no runtime por expiração de sessão OAuth (pre_dispatch_unavailable)."
        },
        {
          "harness": "codex",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "catalog_eligible": false,
          "technical_adequacy": "insufficient",
          "dispatchable": false,
          "cost_basis": "token_price_only",
          "evidence_ids": ["price-terra", "transport-openai"],
          "uncertainty": null,
          "reason": "Mesma família OpenAI da proposta experimental desafiada, violando preferência cross-family do Advisor."
        }
      ],
      "candidates": [
        {
          "harness": "agy",
          "model": "gemini-3.1-pro-high",
          "effort": "high",
          "dispatch_role": "primary",
          "evidence_ids": ["price-flash", "transport-flash"],
          "cost_basis": "token_price_only",
          "reason": "Candidato primário cross-family (Google) elegível e disponível no runtime."
        }
      ]
    }
  }

## Contexto e Fatos
- Trata-se do papel de Advisor (consultivo, modo Debater) do piloto de retomada curta entre ciclos (T023).
- O Advisor debaterá a proposta experimental, o orçamento calibrado (16 reqs globais / sub-teto de 10 em B), a regra ativa fail-closed de parada em run_arms.py e a sanitização estrita de caminhos privados locais antes do congelamento experimental.
- A proposta a ser desafiada utiliza o harness Codex (família OpenAI).
- Conforme prompts/orchestrator-perfis.md, o papel Advisor exige preferência estrita por cross-family (contra-família da proposta desafiada) em sessão limpa isolada.
- O harness Claude (família Anthropic) está fisicamente indisponível no ambiente runtime atual (sessão OAuth expirada / pre_dispatch_unavailable). Portanto, modelos do Claude não podem ser selecionados como primários utilizáveis nesta execução (dispatchable: false).
- Os harnesses comprovadamente disponíveis e funcionais no ambiente são: Codex (OpenAI) e Agy (Google).
- Como a proposta a ser desafiada é OpenAI (Codex), a família Google (Agy) é a candidata cross-family elegível e disponível primária.
- Sem frases de overselection.

## Formato de saída
Responda APENAS com o JSON válido de acordo com o Schema v3. Sem markdown, sem ```json, sem comentários.
