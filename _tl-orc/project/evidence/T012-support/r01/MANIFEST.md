# T012-support r01 — preservação dos artefatos do piloto T012

- **Operação:** preservação por cópia (operação nova em 2026-09-11; não integra a execução original de T012 e não altera T012).
- **Autorização:** usuário, 2026-09-11 (escopo: preservação e preparação documental; sem commit, sem alterações no platform).
- **Captura (UTC):** 2026-09-11T13:38:07Z.
- **Origem (somente leitura, intacta):** `/Users/albertiano/.gemini/antigravity/brain/c35bdc15-8391-494c-8de0-190630cac49e/scratch/t012-pilot`.
- **Destino:** `_tl-orc/project/evidence/T012-support/r01`.
- **Conferência:** 105 entradas; SHA-256 da origem antes da cópia = SHA-256 da cópia = SHA-256 da origem depois da cópia em todas (`all_entries_verified: True`, `origin_untouched_after_copy: True`). Detalhe por arquivo em `manifest.json`.
- **Separação:** a chave de descegamento fica em `05-blinding-key/`, fora de `04-blind-evaluation/` (entradas do avaliador). Quem for reproduzir a avaliação cega não deve abrir `05-blinding-key/`.
- **T012 não é alterada:** `tasks/T012-*.md` e `evidence/T012-r01.md` permanecem como estavam; esta pasta é suporte posterior, sem autoridade de status.

## Inventário preservado (fora do snapshot)

| preservado | origem (relativa ao piloto) | bytes | mtime origem (UTC) | sha256 | papel |
| :--- | :--- | ---: | :--- | :--- | :--- |
| `01-pilot-inputs/short-resume-package.md` | `short-resume-package.md` | 4948 | 2026-09-11T10:18:39Z | `187b793b1c593333…` | entrada do Braço B |
| `01-pilot-inputs/normative-rubric.md` | `normative-rubric.md` | 3299 | 2026-09-11T10:18:44Z | `d4d83a684e6e18ca…` | gabarito congelado (M1–M4, X1–X4) |
| `01-pilot-inputs/arm-a-history.md` | `arm-a-history.md` | 183880 | 2026-09-11T10:39:02Z | `42269f1a7ba33583…` | entrada do Braço A (histórico extraído da sessão b1467fdf, linhas 4407–4595) |
| `02-scripts/prepare-arm-a-context.py` | `prepare-arm-a-context.py` | 2188 | 2026-09-11T10:38:59Z | `f2b0b869c2f6f03c…` | extrator do histórico do Braço A |
| `02-scripts/run-arm-a.py` | `run-arm-a.py` | 6453 | 2026-09-11T10:43:16Z | `5ad03091c105e417…` | executor do Braço A (prompt embutido) |
| `02-scripts/run-arm-b.py` | `run-arm-b.py` | 6726 | 2026-09-11T10:43:24Z | `12e003c8a952b0a7…` | executor do Braço B (prompt embutido) |
| `02-scripts/sanitize-blind-evaluation.py` | `sanitize-blind-evaluation.py` | 7352 | 2026-09-11T10:18:55Z | `42b5f09fe3b38448…` | sanitização e cegamento |
| `02-scripts/review-eval/run-classifier.sh` | `review-eval/run-classifier.sh` | 590 | 2026-09-11T10:58:35Z | `4314b72f27db05b2…` | despacho do Classificador da avaliação |
| `02-scripts/review-eval/run-evaluator.sh` | `review-eval/run-evaluator.sh` | 624 | 2026-09-11T10:59:55Z | `36a398d8f5edfbf8…` | despacho do Avaliador cego |
| `02-scripts/review-eval/validate-classifier.js` | `review-eval/validate-classifier.js` | 1551 | 2026-09-11T10:58:31Z | `490ae2f33656b987…` | validador AJV do resultado do Classificador |
| `03-arm-outputs/raw-decision-A.md` | `raw-decision-A.md` | 21792 | 2026-09-11T10:50:01Z | `35804b23f0541fc1…` | saída bruta do Braço A |
| `03-arm-outputs/raw-decision-A-stderr.txt` | `raw-decision-A-stderr.txt` | 0 | 2026-09-11T10:50:01Z | `e3b0c44298fc1c14…` | stderr do Braço A (vazio) |
| `03-arm-outputs/arm-a-metrics.json` | `arm-a-metrics.json` | 1864 | 2026-09-11T10:50:01Z | `baadc84bc4358708…` | métricas do Braço A (tokens, turnos, tool calls) |
| `03-arm-outputs/raw-decision-B.md` | `raw-decision-B.md` | 34966 | 2026-09-11T10:57:51Z | `4f71b86447ccd45b…` | saída bruta do Braço B |
| `03-arm-outputs/raw-decision-B-stderr.txt` | `raw-decision-B-stderr.txt` | 0 | 2026-09-11T10:57:51Z | `e3b0c44298fc1c14…` | stderr do Braço B (vazio) |
| `03-arm-outputs/arm-b-metrics.json` | `arm-b-metrics.json` | 5443 | 2026-09-11T10:57:51Z | `42e6fbe186761954…` | métricas do Braço B (tokens, turnos, tool calls) |
| `04-blind-evaluation/decision-alpha.md` | `decision-alpha.md` | 21796 | 2026-09-11T10:58:08Z | `a5990ec5326c174d…` | decisão cega Alpha (entrada do avaliador) |
| `04-blind-evaluation/decision-beta.md` | `decision-beta.md` | 34984 | 2026-09-11T10:58:08Z | `d268761c8a0d926d…` | decisão cega Beta (entrada do avaliador) |
| `04-blind-evaluation/classifier-briefing.md` | `review-eval/classifier-briefing.md` | 2892 | 2026-09-11T10:58:21Z | `f0afbb06cfffde0c…` | briefing do Classificador |
| `04-blind-evaluation/classifier-output.json` | `review-eval/classifier-output.json` | 3226 | 2026-09-11T10:59:31Z | `4b4c5888f157f611…` | resultado do Classificador |
| `04-blind-evaluation/classifier-stdout.txt` | `review-eval/classifier-stdout.txt` | 3227 | 2026-09-11T10:59:29Z | `7e36c592faf2bb7c…` | stdout do Classificador |
| `04-blind-evaluation/classifier-stderr.txt` | `review-eval/classifier-stderr.txt` | 0 | 2026-09-11T10:58:40Z | `e3b0c44298fc1c14…` | stderr do Classificador (vazio) |
| `04-blind-evaluation/evaluator-briefing.md` | `review-eval/evaluator-briefing.md` | 62416 | 2026-09-11T11:01:15Z | `856e04a9a973f8df…` | briefing do Avaliador cego (contém Alpha/Beta e gabarito) |
| `04-blind-evaluation/evaluator-stdout.txt` | `review-eval/evaluator-stdout.txt` | 5365 | 2026-09-11T11:03:03Z | `f57b22f552971e3d…` | resultado do Avaliador cego |
| `04-blind-evaluation/evaluator-stderr.txt` | `review-eval/evaluator-stderr.txt` | 90979 | 2026-09-11T11:03:03Z | `ed9b0b7fd4c18a19…` | log do harness Codex do Avaliador |
| `05-blinding-key/blinding-key.json` | `blinding-key.json` | 341 | 2026-09-11T10:58:08Z | `1fdffe625a53ed18…` | chave de descegamento (separada das entradas do avaliador) |

## Snapshot `06-snapshot-dir_A/`

- Cópia integral de `dir_A` (79 arquivos; sem `.git`). `dir_B` tem 79 arquivos e é byte-idêntica a `dir_A` (`dir_B_byte_identical_to_dir_A: True`); não foi duplicada.
- Hash por arquivo em `manifest.json` (entradas com `preserved_relative` sob `06-snapshot-dir_A/`).
- **Aviso operacional:** o snapshot contém uma árvore `_tl-orc/` aninhada (inclusive `STATUS.md` e `PROJECT.md` da época). Ferramentas de descoberta que varram `**/STATUS.md` a partir da raiz do repositório podem encontrá-la; a única instância autoritativa é `_tl-orc/project/STATUS.md` na raiz.

## Não copiados (listados por procedência)

| origem | bytes | sha256 | updatedAt | motivo |
| :--- | ---: | :--- | :--- | :--- |
| `normative-rubric.md.metadata.json` | 169 | `6d775eab9ff300f7…` | 2026-09-11T10:18:44.661749Z | metadados do harness Antigravity |
| `prepare-arm-a-context.py.metadata.json` | 152 | `15514e3f73ee1e59…` | 2026-09-11T10:38:59.469842Z | metadados do harness Antigravity |
| `review-eval/classifier-briefing.md.metadata.json` | 121 | `cb0e37bcc0fd461d…` | 2026-09-11T10:58:21.500289Z | metadados do harness Antigravity |
| `review-eval/evaluator-briefing.md.metadata.json` | 129 | `e6da4451fa7657b3…` | 2026-09-11T10:59:50.829187Z | metadados do harness Antigravity |
| `review-eval/run-classifier.sh.metadata.json` | 119 | `5eddfa8822e4b8da…` | 2026-09-11T10:58:35.787495Z | metadados do harness Antigravity |
| `review-eval/run-evaluator.sh.metadata.json` | 127 | `2c0da433e414c9bb…` | 2026-09-11T10:59:55.430071Z | metadados do harness Antigravity |
| `review-eval/validate-classifier.js.metadata.json` | 134 | `3ba72ceefa921433…` | 2026-09-11T10:58:31.155122Z | metadados do harness Antigravity |
| `run-arm-a.py.metadata.json` | 168 | `92cacb454e3b4bbb…` | 2026-09-11T10:43:16.525578Z | metadados do harness Antigravity |
| `run-arm-b.py.metadata.json` | 168 | `a86a143a9a955a23…` | 2026-09-11T10:43:24.405026Z | metadados do harness Antigravity |
| `sanitize-blind-evaluation.py.metadata.json` | 135 | `195386a26cc3bfa2…` | 2026-09-11T10:18:55.744612Z | metadados do harness Antigravity |
| `short-resume-package.md.metadata.json` | 196 | `d7de562a58608abf…` | 2026-09-11T10:18:39.380446Z | metadados do harness Antigravity |

## Conferências de procedência (feitas na captura, 2026-09-11)

1. **Chave de descegamento × saídas brutas.** `hash_raw_a` = sha256 de `raw-decision-A.md` e `hash_raw_b` = sha256 de `raw-decision-B.md` (confere). `decision-alpha.md` deriva de A e `decision-beta.md` de B, conforme `mapping` da chave.
2. **O snapshot não corresponde a nenhum commit do repositório.** Conferido contra todos os commits até `b06d37e` (HEAD em 2026-09-11): nenhum reproduz os 79 arquivos. Composição observada: (a) `_tl-orc/project/tasks/T009-…md` em estado *simulado* de r02 (`status: in_progress`, `state_revision: 2`, `rework_round: 0`, `content_id: unknown`, `spec_revision: 4197dea48f75cd14`), que não existe em nenhum commit (as revisões versionadas de T009 com essa spec, `2b33cb2` e `f9da501`, já trazem `done`/`state_revision: 9`); (b) `_tl-orc/project/evidence/T009-r02.md` igual à versão versionada; (c) `prompts/`, `schemas/` e `docs/` em estado posterior ao de `f9da501` (2026-09-07 20:25 -03): sete arquivos coincidem com o conteúdo versionado entre `6d33c48` (2026-09-07 20:56 -03) e `42194c0` (2026-09-08 07:52 -03). Ou seja: `dir_A` é uma árvore de trabalho da época do piloto com a Task T009 reescrita para o ponto de corte, **não** o estado histórico exato de T009 r02.
3. **Índice de checksums do pacote curto.** Das 12 entradas com sha256 em `short-resume-package.md`, só `T009-…md` e `T009-r02.md` coincidem com os arquivos de `dir_A`; as outras 10 não coincidem com `dir_A` nem com nenhum commit. O índice foi computado sobre um estado de árvore não identificado; um agente que conferisse esses hashes contra `dir_B` encontraria divergência em 10 de 12.
4. **Leituras do Braço A fora da cópia isolada.** As cinco `tool_calls` registradas em `arm-a-metrics.json` apontam para `/Users/albertiano/thinglab/tl-orchestrator/…` (árvore de trabalho viva do repositório, não `dir_A`); as 20 do Braço B apontam para `dir_B`. O isolamento físico valeu para o diretório de trabalho, não para o alvo das leituras do Braço A; o estado da árvore viva em 2026-09-11 ~10:44–10:50 UTC não está capturado. Consequência: a correspondência histórica do Braço A fica **sujeita a conferência** e não pode ser reconstruída exatamente daqui.
5. **Sensibilidade.** Sem segredos. `arm-a-history.md` contém a substring `sk-notification` (5 linhas: 257, 263, 764, 770, 952) — falso positivo de padrão de chave, é um identificador de mecanismo, não credencial. Caminhos absolutos de `/Users/albertiano/…` (scripts, métricas, `evaluator-stderr.txt`) e 22 UUIDs de sessão são procedência, mantidos sem redação. E-mails: nenhum.
6. **Metadados do harness.** Os `*.metadata.json` do Antigravity não foram copiados; seus `updatedAt` (2026-09-11 10:18–10:59 UTC) e hashes ficam registrados acima como linha do tempo de produção dos arquivos.

## Linha do tempo reconstruída (mtimes de origem, UTC, 2026-09-11)

10:18 pacote curto, rubrica, sanitizador → 10:38–10:39 extrator e `arm-a-history.md` → 10:43 executores A/B → 10:50 saída/métricas A → 10:57 saída/métricas B → 10:58 cegamento (alpha/beta/chave) e briefing do Classificador → 10:59 resultado do Classificador → 11:01 briefing do Avaliador → 11:03 resultado e log do Avaliador.
