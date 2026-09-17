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

## 4. Índice de Fontes Oficiais & Checksums (SHA-256 Verificados)
As seguintes fontes oficiais constituem a base documental da unidade e devem ser conferidas:

| Caminho Relativo | Descrição | SHA-256 |
| :--- | :--- | :--- |
| `_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md` | Especificação e estado da Task T009 | `79fe9df58f3a9dc1aafe73455b67fe50b031116224b902ac1433ee6765481175` |
| `_tl-orc/project/evidence/T009-r02.md` | Parecer oficial íntegro do Checker r02 | `2730e8bd3b03ff81cd5ac2a4a7b79967fec19dc749a8f57fbf9561bb1ca9bf89` |
| `_tl-orc/PROJECT.md` | Política de governança e perfis locais | `3b0620be3a576da4d93494d726548368322f0735313de5c81a2223d25bf89fe7` |
| `prompts/orchestrator.md` | Contrato do papel Orquestrador | `2735b3ce7a6973726f973c126149ee832f9faed06ece3aabe06ac73d5560939e` |
| `prompts/orchestrator-perfis.md` | Perfis de despacho e regras de independência | `ac296a8b07affa98360611f123bae5bf6e7696f5d884dc24bb745f9633220842` |
| `prompts/orchestrator-playbook.md` | Playbook de condução e ciclos | `ed57a254cf3c0a1d4daa8046c186147a527f080d3362e88ceafb21a262060f24` |
| `prompts/maker.md` | Contrato do papel Maker | `e24be10829ed3284d76ce42d37f7fc31b8f4c9aaaa30bd2b96ac6861ac216d4e` |
| `prompts/checker-report-only.md` | Contrato do papel Checker | `85a71b904fe8e9133bf6bf6f785ee8c7c4b0f800b312e714778d790f6e66583f` |
| `schemas/review-result.schema.json` | Schema do parecer do Checker | `4cfb98cf8a2994edc152c2406ada4cea6da2e8f859d1a6d3c53306356fbb6a48` |
| `schemas/classification-result.schema.json` | Schema do resultado da classificação | `455f655442dd2aed4ba3fc475ea7650456df7bb1734659bea6aab428ca8379f7` |
| `docs/WORK_MODEL.md` | Modelo de trabalho e ciclo de vida de tarefas | `310d2ec32b12e6142f2e561e32c8c63af7de4a1ee62f5e63a8d90d9e2945c14e` |
| `docs/MODEL_ROUTING.md` | Cartões e catálogo oficial de roteamento | `28f8bc9c76a24af57fc2efaea6d589b75ecc6c22d298ec73248db5b35c259abf` |
