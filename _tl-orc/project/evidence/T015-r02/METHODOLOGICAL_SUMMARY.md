# Resumo Metodológico e Resultados Experimentais — Task T015 (Rodada r02)

Este documento sintetiza os resultados empíricos, o protocolo experimental e os limites de interpretação científica dos seis replays pareados executados para a Task Native `T015` (`context economy, selective retrieval e handoff verificável`) na rodada `r02`.

---

## 1. Protocolo Experimental e Isolamento de Ambientes

O experimento foi conduzido em ambiente estritamente controlado com segregação física de worktrees e pré-declaração criptográfica:

- **Braço de Referência (Baseline):** congelado no commit base `3e9ecc356b839dbe5e736e5356219bb092a4ff00` (anterior à introdução de T015), operando com as ferramentas padrão do método (`Read`, `Glob`, `Grep`, `Bash`) e briefing com diretriz de inspeção direta.
- **Braço T015-r02:** congelado no commit `511e745db78b9c87f6d504e57d883f9e79c2445d` (contendo a implementação do Maker r02 que resolveu os apontamentos R1–R5), operando com selective retrieval via `scripts/read_section.py`, manifesto de retomada resolvido `resume.json` e as mesmas ferramentas disponíveis.
- **Harness e Modelo:** Claude 3.7 Sonnet (`claude-sonnet-5`), effort `medium`, temperatura operacional idêntica.
- **Entradas dos Checkpoints:** byte-idênticas entre os dois tratamentos para cada checkpoint (A', B e C), validadas por SHA-256 contra os manifestos canônicos antes de cada despacho (Portão AC15).
- **Auditoria Endurecida de Confinamento (AC16):** utilização de auditor canônico com conferência de `realpath` estrita contra raízes autorizadas (`allowed_set` pré-declarado com hash criptográfico), parser de comandos Bash (`read_section.py`, `cat`, `head`, `sed`, `grep`), isolamento de blocos *heredoc* e remoção de qualquer inclusão implícita de diretórios de suporte do sistema.

---

## 2. Conclusões Científicas Admissíveis

A análise rigorosa dos seis replays estabelece quatro conclusões definitivas:

### 2.1. Qualidade e Equivalência Substantiva
- Nos Checkpoints A' e B, ambos os braços (Referência e T015-r02) apresentaram equivalência substantiva integral, atingindo 100% das rubricas de mérito da tarefa e formulando propostas de condução perfeitamente alinhadas à governança.
- No Checkpoint C, o braço T015 atingiu mérito formal correto de condução. O braço de Referência também atingiu uma decisão substantiva correta, porém seu processo de busca foi contaminado experimentalmente por violação das restrições de confinamento (AC16).

### 2.2. Eficiência de Contexto e Trade-Offs
- **Checkpoint A' (Vitória Clara de T015):** redução de **43,3%** nos bytes entregues por ferramentas (55.893 B vs 98.659 B), redução de **30,0%** em criação de cache (124.299 vs 177.636 tokens), redução de **53,3%** em leitura de cache (508.292 vs 1.089.418 tokens) e redução de **10,6%** no tempo total de resposta (157,20s vs 175,77s).
- **Checkpoint B (Trade-off de Protocolo):** redução brutal de **69,5%** nos bytes entregues por ferramentas (14.401 B vs 47.168 B) e redução de **30,2%** na criação de cache (54.567 vs 78.179 tokens). Contudo, o protocolo seletivo exigiu maior overhead interativo do modelo: aumento de **57,1%** nos turnos (22 vs 14), aumento de **52,6%** na latência de sessão (109,31s vs 71,63s), aumento de **58,5%** nos tokens de saída (23.799 vs 15.011) e aumento de **80,3%** na leitura cumulativa de cache (458.169 vs 254.063 tokens).
- **Checkpoint C:** não fornece delta de eficiência válido para comparação pareada devido à invalidação metodológica do braço de Referência.
- **Conclusão de Eficiência:** Não há base para afirmar "redução universal de tokens/cache/latência". O mecanismo é altamente eficaz para redução de volume entregue (-43% a -70%), mas o custo interativo do protocolo seletivo depende substancialmente da estrutura do artefato e do padrão de inspeção do modelo.

### 2.3. Robustez e Confinamento (AC16)
- O Checkpoint C fornece evidência forte de que o mecanismo T015 impediu a dispersão exploratória e o vazamento de contexto fora das fontes congeladas.
- O braço de Referência recorreu a uma busca desassistida com `Glob("**/*")` a partir da raiz, recebendo 292 bytes de metadados externos fora do conjunto permitido (`reads_outside = ['.']`) e tentando executar uma busca por `grep` contra uma raiz de repositório externa viva (`disallowed_external_attempts`).
- O braço T015-r02 manteve confinamento estrito de 100%: zero leituras externas, zero tentativas externas não autorizadas e zero bytes vazados.

### 2.4. Offloading e Compacting de Ferramentas (AC09 / AC10)
- **Registro Metodológico Mandatório:** em todos os seis replays, **Raw Tool Result Bytes = Delivered Tool Result Bytes** (`Tool Delivery Ratio = 1.00`).
- Os replays empíricos deste benchmark avaliaram estritamente o mecanismo de **selective retrieval** (leitura seletiva de seções via `read_section.py` orientada por `resume.json`), e **NÃO mediram benefício empírico de compactação/offloading de resultados de ferramentas**.
- Os critérios AC09 e AC10 continuam sustentados e formalmente verificados pela suíte de testes determinísticos unitários (`scripts/tests/test_extract_tool_result.py`), contendo sondas contrafactuais com mutação de payload e garantia de *losslessness* para falhas, e não pelos replays pareados.

---

## 3. Tabela Comparativa Consolidada dos Replays r02

| Métrica | A' Ref | A' T015 | Δ A' (%) | B Ref | B T015 | Δ B (%) | C Ref (Inv.) | C T015 | Validade C |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Turnos** | 26 | 19 | **-26,9%** | 14 | 22 | **+57,1%** | 20 | 22 | Incomparável |
| **Tool Calls** | 15 | 10 | **-33,3%** | 8 | 10 | **+25,0%** | 10 | 12 | Incomparável |
| **Wall Clock (s)** | 175,8 | 157,2 | **-10,6%** | 71,6 | 109,3 | **+52,6%** | 102,3 | 143,4 | Incomparável |
| **Observed Reads** | 7 | 6 | **-1** | 7 | 8 | **+1** | 6 | 10 | Incomparável |
| **Raw Tool Bytes** | 98.659 | 55.893 | **-43,3%** | 47.168 | 14.401 | **-69,5%** | 43.436 | 41.204 | Incomparável |
| **Delivered Tool Bytes** | 98.659 | 55.893 | **-43,3%** | 47.168 | 14.401 | **-69,5%** | 43.436 | 41.204 | Incomparável |
| **Tool Delivery Ratio** | 1,00 | 1,00 | **0,0%** | 1,00 | 1,00 | **0,0%** | 1,00 | 1,00 | Sem offloading |
| **Cache Creation** | 177.636 | 124.299 | **-30,0%** | 78.179 | 54.567 | **-30,2%** | 61.749 | 98.245 | Incomparável |
| **Cache Read** | 1.089.418 | 508.292 | **-53,3%** | 254.063 | 458.169 | **+80,3%** | 465.356 | 536.836 | Incomparável |
| **Output Tokens** | 34.267 | 33.085 | **-3,4%** | 15.011 | 23.799 | **+58,5%** | 19.298 | 29.243 | Incomparável |
| **Reads Outside Allowed** | [] | [] | **0** | [] | [] | **0** | `['.']` (292 B) | [] | **AC16 FAIL Ref** |
| **Disallowed Ext. Calls** | [] | [] | **0** | [] | [] | **0** | 1 (grep ext) | [] | **AC16 FAIL Ref** |
| **Validade Eficiência** | VÁLIDO | VÁLIDO | **Par Válido** | VÁLIDO | VÁLIDO | **Par Válido** | **INVÁLIDO** | **INVÁLIDO** | **Sem delta** |
| **Validade Robustez** | PASS | PASS | **PASS** | PASS | PASS | **PASS** | **FAIL (violação)** | **PASS** | **Evidência T015** |

---

## 4. Preservação de Rastreabilidade e Cegamento

- **Bundle de Revisão Cego (`review-bundle/`):** estruturado por checkpoint e braço (`Alpha`/`Beta`), com todos os caminhos normalizados para `<repo-root>`, UUIDs anonimizados e marcas de tratamento ofuscadas.
- **Chave de Cegamento r02 (`blinding/blinding-key.json`):**
  - Checkpoint A: Alpha = `t015`, Beta = `reference`
  - Checkpoint B: Alpha = `reference`, Beta = `t015`
  - Checkpoint C: Alpha = `t015`, Beta = `reference`
- **Registro Explícito no Bundle de C:** `C/Beta` (Referência) traz expressamente `experimental_validity: {"efficiency": "invalid", "robustness": "valid_failure"}`; `C/Alpha` (T015) traz `experimental_validity: {"efficiency": "invalid", "robustness": "valid_pass"}`.
- **Harness e Suporte de Auditoria (`audit-support/`):** scripts exatos preservados e vinculados por SHA-256 em `audit-support-manifest.json`, garantindo reproducibilidade integral e auditabilidade sem contaminação dos 15 `content_paths` da entrega.
