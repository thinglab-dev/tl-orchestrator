# Evidência Sintética de Indisponibilidade de Infraestrutura (T009 R4)

Registro sintético de indisponibilidade de infraestrutura para controle do piloto de fallback de mesma família sob política preferred.

## Agent runs
| run_id | role | harness | model | effort | family | session | phase | round | outcome | fallback_reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| synth-run-codex-01 | checker | codex | gpt-6-astra | high | OpenAI | 01a07000-0000-0000-0000-000000000001 | review | r01 | infra_failure: 503 Service Unavailable (OpenAI endpoint timeout) | infra_unavailable |
| synth-run-claude-02 | checker | claude | sonnet | high | Anthropic | 01a07000-0000-0000-0000-000000000002 | review | r01 | infra_failure: 429 Rate limit exceeded / account quota exhausted | infra_unavailable |
