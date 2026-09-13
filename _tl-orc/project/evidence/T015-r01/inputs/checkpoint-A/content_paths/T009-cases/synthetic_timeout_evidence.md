# Evidência Sintética de Timeout (Controle Negativo R3)

## Agent runs
| run_id | role | harness | model | effort | family | session | phase | round | outcome | fallback_reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| synth-timeout-codex-01 | checker | codex | gpt-6-astra | high | OpenAI | 01a07000-0000-0000-0000-000000000099 | review | r01 | infra_failure: 504 Gateway Timeout (request timed out) | timeout |
| synth-timeout-claude-02 | checker | claude | sonnet | high | Anthropic | 01a07000-0000-0000-0000-000000000098 | review | r01 | infra_failure: 429 insufficient_quota | infra_unavailable |
