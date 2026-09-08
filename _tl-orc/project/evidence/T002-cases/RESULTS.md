# Resultados da medição AC03 (executada pelo Orquestrador em 2026-09-08)

Condições: Codex `gpt-5.6-luna`, `model_reasoning_effort=medium`, sandbox read-only, sessões novas (`codex exec`), sem correção; mesma intenção sintética (fase debate, story_id null, papéis planner/maker/checker) e mesmo catálogo (perfil de despacho do repositório fonte, `_tl-orc/PROJECT.md`). Briefings em `briefing-prosa-N.md` (campos descritos em prosa, sem esqueleto) e `briefing-minimo-N.md` (mesmas entradas + esqueleto literal gerado por `T002-briefing-skeleton.py` com as cadeias do fonte + regras fixas). Conferência mecânica em duas camadas, com as implementações preservadas em `T002-cases/tools/`: estrutura por `tools/check_struct.py` (validador mínimo sem dependências: type/enum/const/required/additionalProperties/items/minItems/maxItems/uniqueItems/minLength/$ref/allOf/if-then/not sobre o schema real) e catálogo/cadeias/pins/IDs por `tools/mech_check.py` (protótipo mecânico usado nas classificações de T009/T010; lê `_tl-orc/PROJECT.md` do repositório fonte) com o arquivo de expectativas `tools/expected-medicao.json`. Os arquivos `check-*.txt` separam a saída literal de cada validador da interpretação do Orquestrador.

| chamada | sessão Codex | início → fim UTC | estrutura | catálogo/cadeias/pins/IDs | defeitos da primeira resposta |
| :--- | :--- | :--- | :--- | :--- | :--- |
| prosa-1 | 01a07e99-d6b0-7343-93d5-72e66adaa2d9 | 20260908T012006Z → 20260908T012043Z | inválida | n/a | JSON malformado (objeto fechado antes de confidence); 'version' em vez de schema_version; revisões ausentes; tier fora do enum |
| prosa-2 | 01a07e9a-67fa-7233-8d3d-8c6869649da1 | 20260908T012043Z → 20260908T012132Z | inválida | rejeitada | schema_version/context_revision/catalog_revision ausentes; propriedade extra 'version'; tier fora do enum |
| prosa-3 | 01a07e9b-2a73-7d53-8c91-7be8cf144f20 | 20260908T012132Z → 20260908T012212Z | inválida | n/a | JSON malformado (objeto fechado antes de confidence); 'version' em vez de schema_version; revisões ausentes; tier fora do enum |
| minimo-1 | 01a07e9b-c78f-7442-9e5c-fef54d68754e | 20260908T012212Z → 20260908T012246Z | válida | aceita | — |
| minimo-2 | 01a07e9c-46f3-7a50-9412-53ae8b2f9516 | 20260908T012246Z → 20260908T012317Z | válida | aceita | — |
| minimo-3 | 01a07e9c-c1d3-7e50-a5c7-19b9e359fe1f | 20260908T012317Z → 20260908T012350Z | válida | aceita | — |

## Comandos executados (reprodução da conferência sobre as respostas preservadas; uma nova medição exige novas chamadas pagas)

Diretório de execução: raiz do repositório fonte (worktree). Chamadas, uma por briefing, em sessão nova, com o briefing inteiro pela entrada padrão:
```bash
codex exec -s read-only -m gpt-5.6-luna -c 'model_reasoning_effort="medium"' -c 'approval_policy="never"' --output-last-message <saida>.txt - < _tl-orc/project/evidence/T002-cases/briefing-<prosa|minimo>-<N>.md
```
Normalização permitida: remoção de uma cerca markdown ` ```json ` / ` ``` ` quando presente na última mensagem (nenhuma outra edição); o resultado é `resposta-<prosa|minimo>-<N>.json`. Conferência:
```bash
python3 _tl-orc/project/evidence/T002-cases/tools/check_struct.py schemas/classification-result.schema.json _tl-orc/project/evidence/T002-cases/resposta-<...>.json
python3 _tl-orc/project/evidence/T002-cases/tools/mech_check.py _tl-orc/project/evidence/T002-cases/resposta-<...>.json _tl-orc/project/evidence/T002-cases/tools/expected-medicao.json
```
Esqueleto dos briefings mínimos: `python3 _tl-orc/project/evidence/T002-briefing-skeleton.py schemas/classification-result.schema.json --roles planner,maker,checker --chain planner=claude,codex,agy --chain maker=agy,codex,claude --chain checker=codex,claude,agy`.

## Limite sobre a procedência dos IDs locais
Os quatro IDs `local-*` dos briefings foram fornecidos com referência genérica aos relatórios de origem; eles não constam na primeira coluna de uma tabela estruturada nesses arquivos, como exige a tabela de procedência (`prompts/orchestrator-perfis.md`, Briefing concreto). A conferência mecânica verificou apenas que as respostas usaram IDs do conjunto fornecido; ela não comprova a procedência normativa desses IDs. Esse limite vale igualmente para as duas condições e não afeta a comparação estrutural.

Totais: prosa 0/3 válidas na primeira resposta (2 JSON malformados, 1 estruturalmente inválido); mínimo 3/3 válidas na primeira resposta (estrutura e catálogo). Limites: N = 3 por condição, um modelo, um effort, uma intenção, um catálogo; as respostas mínimas não foram avaliadas quanto à pertinência de julgamento (tier, reason), só quanto à conformidade mecânica. Respostas literais em `resposta-*.json` (cerca markdown removida quando presente); as tabelas de conferência por chamada estão em `check-*.txt`.
