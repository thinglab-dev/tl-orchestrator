# Briefing de Classificação: Papel Checker (Task T032 - Phase B)

Você é o Classificador do tl-orchestrator operando sob o Schema v3 (Minimum Sufficient Capability).
Sua função nesta chamada é classificar o papel Checker na fase review para a Task T032 e emitir APENAS um único bloco JSON válido estritamente conforme o schema schemas/classification-result-v3.schema.json.

## Parâmetros e Contexto
- story_id: "T032"
- phase: "review"
- context_revision: "tl-orchestrator@66401c8"
- catalog_revision: "PROJECT.md-2026-09-07"
- checker_independence: required
- effective_authors: ["google", "anthropic"]

## Fatos Relevantes
1. Task T032 institucionaliza o Protocolo de Retomada Curta e Transição entre Ciclos com `deliverable: package`.
2. A regra mandatória da task é `checker_independence: required`.
3. A autoria efetiva é mista: Phase A (Google), Advisor substantive rework (Anthropic Claude), Phase B Maker (Google).
4. Sob `checker_independence: required`, qualquer modelo das famílias Google e Anthropic é estritamente inelegível.
5. O único candidato cross-family independente remanescente no catálogo é OpenAI Codex (`gpt-5.6-terra` / effort `high`).
