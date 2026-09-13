# Pacote Curto de Retomada (Índice Aberto de Navegação)

> [!IMPORTANT]
> Este pacote atua estritamente como **índice derivado de navegação e conferência obrigatória**, sem autoridade normativa própria nem presunção de veracidade. Todas as decisões de condução devem ser fundamentadas pela inspeção direta das fontes oficiais apontadas abaixo.

## 1. Identidade Qualificada Completa
- `active_work_ref`: `native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md`
- `fase_corrente`: `rework` (ou proposição da próxima fase após `review` r02 com `changes_requested`)
- `state_revision`: 2
- `spec_revision`: 4197dea48f75cd14
- `content_id`: 0de10d60149cf7c038a0954c6aec302c9fcd111e:97b3612674fa4aa5
- `rework_round`: 2 (concluído; próximo ciclo é rework 3 ou escalonamento consultivo)

## 2. Governança & Política Ativa
- `politica_path`: `_tl-orc/PROJECT.md`
- `instrucao_usuario`: "Autorizo executar a T009 como analysis com o piloto delimitado"
- `branch_autorizada`: `analysis/t009-semantic-validation`
- `escopo_autorizado`: Somente os `content_paths` de T009 (`_tl-orc/project/evidence/T009-analysis.md`, `_tl-orc/project/evidence/T009-mechanical-check.py`, `_tl-orc/project/evidence/T009-cases`). Proibida alteração de arquivos do pacote distribuído ou escrita fora de evidência do projeto.
- `pins_e_restricoes`: Checker com restrição `required` e família distinta de toda autoria efetiva (participantes na autoria: Google e Anthropic).

## 3. Estado Operacional da Unidade
- `veredito_rodada_anterior`: `changes_requested`
- `parecer_checker_ref`: `_tl-orc/project/evidence/T009-r02.md`
- `resumo_achados_checker`:
  - **R1 (high, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:130` — AC02: ocorrência textual de um ID ainda é aceita como registro de medição local, inclusive com âncora ou linha inexistente.
  - **R2 (high, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:488` — AC02: derivação de proxy aceita menção a tarefa sem requisito de custo e ignora escopo delimitado no cartão.
  - **R3 (high, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:431` — AC03: fallback de independência aceita texto arbitrário como prova de indisponibilidade e seleciona candidato indisponível.
  - **R4 (high, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:570` — AC03: família desconhecida é tratada como distinta, permitindo contornar required.
  - **R5 (medium, patch, maker)**: `_tl-orc/project/evidence/T009-mechanical-check.py:514` — AC03: ausência de família independente sob required virou defeito mecânico do objeto, contrariando a separação entre validade e resolução.
- `proximo_passo_previsto`: Propor formalmente o encaminhamento da unidade (rework ou escalonamento consultivo fundamentado) e preparar o briefing correspondente em modo somente leitura (sem despacho efetivo).

## 4. Índice de Fontes Oficiais & Checksums (SHA-256)
As seguintes fontes oficiais constituem a base documental da unidade e devem ser conferidas:

| Caminho Relativo | Descrição | SHA-256 |
| :--- | :--- | :--- |
| `_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md` | Especificação e estado da Task T009 | `79fe9df58f3a9dc1aafe73455b67fe50b031116224b902ac1433ee6765481175` |
| `_tl-orc/project/evidence/T009-r02.md` | Parecer oficial íntegro do Checker r02 | `2730e8bd3b03ff81cd5ac2a4a7b79967fec19dc749a8f57fbf9561bb1ca9bf89` |
| `_tl-orc/PROJECT.md` | Política de governança e perfis locais | `3b0620be3a576da417551062b1660d5e1ba09307cf8f416d84989e782a22284b` |
| `prompts/orchestrator.md` | Contrato do papel Orquestrador | `2735b3ce7a697372cf93b964955b23d9a0dffbe901760dd073c6837ca7fba305` |
| `prompts/orchestrator-perfis.md` | Perfis de despacho e regras de independência | `ac296a8b07affa98bf8c991db1aa6576629f6d7dd5ea2360b54fca64bb13a35c` |
| `prompts/orchestrator-playbook.md` | Playbook de condução e ciclos | `ed57a254cf3c0a1de8155998df9ca9fc21345d817fc1cecf1aa06a13d78da0ff` |
| `prompts/maker.md` | Contrato do papel Maker | `e24be10829ed328404a7bc9ec3ba2b757e7eb1568270c53d0e2e0ea48148b598` |
| `prompts/checker-report-only.md` | Contrato do papel Checker | `85a71b904fe8e9134a66e40d6cfa92809e3ca31b53e70d4c1cf604084f707f15` |
| `schemas/review-result.schema.json` | Schema do parecer do Checker | `4cfb98cf8a2994ed91b5c479320e4eb171fc82d5440d9bdf11f26f2a6321bb46` |
| `schemas/classification-result.schema.json` | Schema do resultado da classificação | `455f655442dd2aedf3b16952e42bca0d39e24748db0d757dc55c064998c61eb6` |
| `docs/WORK_MODEL.md` | Modelo de trabalho e ciclo de vida de tarefas | `310d2ec32b12e614d95c73d9ec9d81d2dfbd4205562d989f6631e5f8fe9ef87b` |
| `docs/MODEL_ROUTING.md` | Cartões e catálogo oficial de roteamento | `28f8bc9c76a24af5d4a4ae7a61d155877c44917457fc88a101b7a2d4fa55231c` |
