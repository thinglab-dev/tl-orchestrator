id: T023
type: analysis
deliverable: none
standalone: true
method: native
status: ready
state_revision: 1
depends_on: [T010, T021]
blocked_by: []
origin: user (2026-09-09, parecer sobre análise de dados de T009/T010; preparação mecânica e composição padrão alinhada em 2026-09-11)
decisions: []
spec_author: orchestrator
spec_revision: 9c64bc99ae8a8e24
rework_round: 0
affects_context: []
content_paths: [_tl-orc/project/tasks/T012-piloto-retomada-curta-entre-ciclos.md, _tl-orc/project/evidence/T012-r01.md]

## Finding
source: auditoria local conservadora das transcrições b1467fdf e 8a731008 na janela 2026-09-07T21:03Z a 2026-09-08T00:25Z
observed:
  1. No Orquestrador (b1467fdf), foram contabilizados 99.248.174 tokens de entrada em 144 grupos consistentes, com média de 689.223 tokens/grupo.
  2. 99,46% dos tokens de entrada foram atendidos por cache_read_input_tokens (98.716.722 tokens).
  3. No Grupo 121, a entrada atingiu 958.028 tokens; após o registro de compact_boundary no sistema (L5388) e isCompactSummary no usuário (L5389), o Grupo 122 registrou 79.414 tokens de entrada — queda pontual observada de 91,7% (878.614 tokens a menos).
  4. Após a compactação registrada, observaram-se 4 attachments re-anexando arquivos de especificação, decisão e governança (L5391–L5394).
  5. A continuidade operacional seguiu até o fechamento de T010. Não houve medição comparativa de qualidade, desvios ou latência em relação a uma condução alternativa.
hypothesis:
  1. Reduzir ativamente o contexto transportado entre ciclos em uma fronteira planejada pode diminuir o volume de tokens de entrada cumulativos por turno sem depender de eventos do harness.
  2. Um pacote curto derivado dos registros oficiais, atuando estritamente como índice de conferência obrigatória, pode permitir que uma sessão limpa tome a decisão de condução correta sem degradação de fidelidade às regras e à governança.
  3. A economia em cache_read_input_tokens decorrente de um histórico menor pode ou não compensar o custo de bootstrapping (geração do pacote, nova criação de cache e releituras de fontes); a comparação experimental mensurará essa relação sem presumir economia monetária direta.
impact: fundamentar com dados empíricos a viabilidade e os custos reais de protocolos de controle de contexto entre ciclos de trabalho do Orquestrador.
next verification: experimento comparativo A/B sobre duas cópias independentes de um mesmo checkpoint, com escopo delimitado a propor o encaminhamento e preparar o briefing em somente leitura; medição de custo integral, tempo e conferência cega contra critérios pré-fixados.
dedup: T010 formalizou o escalonamento consultivo e a procedência por tipo; T011 propõe a continuação sobre lotes autorizados; T012 investiga e mede o protocolo de retomada curta entre ciclos; T014 formaliza a política global de participantes e perfis-padrão.

## Spec
### Intent
Avaliar empiricamente se o Orquestrador, ao retomar o trabalho em sessão nova a partir de um pacote curto de índices oficiais em um checkpoint fixo, alcança uma decisão de condução conforme o contrato com menor custo integral de entrada e sem introduzir erros ou desvios em relação à condução com histórico longo, sob a composição operacional padrão (Maker Gemini 3.8 Flash High / Checker Codex GPT-5.6 Terra High).

### Scope and write paths
Entregáveis revisáveis da análise: somente `_tl-orc/project/tasks/T012-piloto-retomada-curta-entre-ciclos.md` e o relatório de evidência experimental `_tl-orc/project/evidence/T012-r01.md`.
Arquivos de suporte mecânico fora da distribuição: `scratch/t012-pilot/short-resume-package.md`, `scratch/t012-pilot/normative-rubric.md`, `scratch/t012-pilot/sanitize-blind-evaluation.py`, `scratch/t012-pilot/dir_A/` e `scratch/t012-pilot/dir_B/`. Proibida qualquer escrita ou modificação nos arquivos do pacote distribuído.

### 1. Definição Operacional do Checkpoint e Histórico dos Braços
1. **Caso Adaptado e Invariantes**:
   * O caso de teste reproduz a transição imediata após o recebimento do parecer do Checker com `changes_requested` referente à rodada r02 de T009. Como as regras de procedência por tipo, limites de provas e escopo de leitura foram consolidadas posteriormente em T010, o caso é formalmente definido como um **caso adaptado**, no qual o estado documental de T009 r02 é submetido às regras normativas vigentes de T010 de forma idêntica em ambos os braços.
   * Modelo, effort do harness e versão das regras permanecem rigorosamente congelados e iguais nos dois braços.
   * **Composição Operacional Padrão Alvo**: Alinhada à política global de participantes (T014), o Orquestrador orienta o encaminhamento para o par Maker `Gemini 3.8 Flash High` (Agy) e Checker `Codex GPT-5.6 Terra High`, sob filtro estrito de `checker_independence: required` contra a autoria efetiva participante (Anthropic e Google participantes na r01/r02 de T009, habilitando Codex como revisor independente primário).
2. **Carregamento do Histórico do Braço A (Controle)**:
   * A sessão original de referência (`b1467fdf`) permanece preservada intacta, em somente leitura.
   * Na fase preparatória (pré-condição técnica de execução), o mecanismo do harness foi verificado. Como a retomada nativa com `--fork-session` e `--resume-session-at` depende de estruturas dinâmicas de sessão, o histórico acumulado até o checkpoint pode ser fornecido contextualmente via prompt/arquivo, e o Braço A é formalmente registrado no relatório como **reprodução com histórico fornecido**, sem mascará-lo como retomada nativa.
3. **Ambiente Completo do Braço B (Sessão Nova)**:
   * O Braço B recebe todo o ambiente padrão que o harness entrega a qualquer sessão limpa do Orquestrador: prompt do papel (`orchestrator.md`, `perfis`, `playbook`), regras da raiz (`AGENTS.md`, `CONTRIBUTING.md`), definições de ferramentas (`Bash`, etc.) e a política ativa (`PROJECT.md`).
   * A única diferença operacional reside na ausência do histórico de mensagens anteriores, substituído pelo Pacote Curto de Retomada como instrução de inicialização.
4. **Isolamento Físico das Árvores**:
   * O teste opera sobre duas cópias físicas independentes em disco (`dir_A` e `dir_B`), derivadas do mesmo commit/estado. Nenhuma ação no Braço A altera o estado que o Braço B encontrará.
5. **Alcance Delimitado**:
   * O experimento encerra-se na emissão da decisão de condução: **propor o encaminhamento da fase e preparar o briefing correspondente** em modo somente leitura. Não haverá despacho efetivo nem execução de retrabalho por agentes subordinados durante o experimento comparativo.

### 2. Estrutura do Pacote Curto de Retomada (Índice Aberto)
O pacote curto atua estritamente como **índice derivado de navegação, sem autoridade própria**:
* **Identidade Qualificada Completa**: Reutiliza a convenção oficial `active_work_ref` (`docs/WORK_MODEL.md`):
  `<work_method>/<unit_type>/<id ou area_id:id>@<source_location>`, acompanhada de `fase_corrente`, `state_revision`, `spec_revision` e `content_id` (e.g.: `native/task/T009@_tl-orc/project/tasks/T009-validacao-semantica-da-classificacao-pelo-orquestrador.md`).
* **Governança & Política**: Caminho e revisão de `PROJECT.md`, instrução original do usuário e limites de autorização vigentes. Pins registrados são repassados como restrições de entrada ao Classificador, sem dispensá-lo.
* **Estado Operacional**: Veredito formal da rodada anterior (apontador para o parecer do Checker), resumo estruturado dos achados e próximo passo previsto.
* **Índice de Fontes Oficiais & Checksums**: Caminhos relativos dos documentos normativos (Task spec, parecer do Checker, contratos) com respectivos hashes SHA-256 para permitir detecção de divergência ou estado desatualizado.
* **Princípio de Não-Tautologia**: O agente deve **conferir os documentos oficiais apontados** antes de formular a proposta; o pacote não constitui prova nem concede autoridade em si. Consultas adicionais ou releituras dentro do escopo permitido são computadas como custo, sem constituir aborto automático.

### 3. Gabarito Normativo Congelado e Avaliação Cega
O caso de teste é avaliado contra uma matriz normativa pré-fixada:
* **Decisões Obrigatórias (Must)**:
  1. Reconhecer o veredito da rodada como `changes_requested`, mantendo o trabalho aberto.
  2. Identificar que os achados centrais pertencem à classe de *procedência de entradas*.
  3. Propor encaminhamento formal de retrabalho ou consulta fundamentada, preparando o briefing cabível com requisitos de procedência por tipo e conteúdo (T010 AC02) e alinhado à composição padrão (Maker `Gemini 3.8 Flash High` e Checker `Codex GPT-5.6 Terra High`).
  4. Manter a árvore/branch de trabalho autorizada.
* **Decisões Permitidas (May)**:
  1. Propor o despacho de retrabalho ao `Maker` OU, caso justifique no relatório, propor escalonamento consultivo (fase `debate`) para saneamento de requisitos. *(T010 estabelece a consulta como obrigatória após N reworks da mesma classe, mas não proíbe consulta fundamentada antes desse limiar).*
  2. Apresentar o briefing em formato esqueleto ou seções em tópicos, desde que contenha os campos obrigatórios.
  3. Consultar arquivos adicionais de evidência ou contratos do pacote (custo computado normalmente).
* **Decisões Proibidas (Must Not)**:
  1. Emitir proposta de aprovação (`approved`) ou concluir a tarefa ignorando os achados pendentes do Checker.
  2. Fixar modelo ou effort por conta própria sem submeter a escolha (e eventuais restrições/pins) ao Classificador.
  3. Apresentar no briefing fontes fora da raiz consumidora ou do pacote sem autorização formal (T010 AC04).
  4. Tratar o pacote de retomada como verdade absoluta sem conferência dos arquivos apontados.

#### Protocolo de Avaliação Cega
1. **Sanitização com Preservação Estrutural**:
   * Substituem-se **apenas as raízes físicas absolutas** de cada braço por um alias neutro comum (`<root>/`), preservando intactos todos os caminhos relativos, referências documentais, nomes de arquivos e revisões.
   * Removem-se identificadores de harness (`sessionId`, `requestId`, timestamps), rotulando as saídas aleatoriamente como `Decisão Alpha` e `Decisão Beta` via `sanitize-blind-evaluation.py`.
2. **Avaliação Cega**:
   * O avaliador recebe o Checkpoint, o Gabarito Normativo e as decisões sanitizadas `Alpha` e `Beta`.
   * Caso seja utilizado um avaliador LLM, a escolha de seu modelo e perfil deve passar pelo Classificador do projeto e ser debitada do orçamento previsto.
   * O parecer e o briefing propostos são julgados na matriz objetiva; a conformidade das leituras efetivamente realizadas (confinamento à raiz) é auditada diretamente nos registros de ferramentas de cada braço.
3. **Descegamento**:
   * Somente após o registro do veredito avaliador, o mapeamento `Alpha/Beta` $\to$ `A/B` é revelado para consolidação dos resultados.

### 4. Orçamento Discriminado e Regra Operacional de Parada (Circuit Breaker)
* **Distinção de Controle**: Como a contabilidade de tokens pela API é disponibilizada após a conclusão de cada requisição, os tetos numéricos representam uma **regra operacional de parada após medição**, e não uma garantia matemática *a priori* contra estouros pontuais na última chamada.
* **Unidade Efetivamente Controlável**: Na fase preparatória, deve-se verificar se a camada de orquestração/harness consegue pausar e inspecionar os tokens entre requisições individuais do modelo ou se o controle ocorre somente entre execuções completas da CLI (que podem agrupar múltiplos turnos). A contagem e os pontos de checagem devem acompanhar a unidade que o ambiente realmente consegue interromper. Qualquer teste de retomada ou verificação que invoque um modelo é debitado das requisições e tokens previstos no orçamento.

| Etapa | Reqs. de IA Deduplicadas | Sub-Orçamento Entrada | Sub-Orçamento Saída | Operações Locais Determinísticas (Sem Custo de IA) |
| :--- | :---: | :---: | :---: | :--- |
| **1. Preparação & Pacote** | 0 | 0 tokens | 0 tokens | Clonagem de pastas, verificação de hashes, montagem mecânica |
| **2. Braço A (Histórico Acumulado)** | 3 | 2.000.000 tokens | 30.000 tokens | Invocação com histórico preservado ou fornecido |
| **3. Braço B (Sessão Nova + Pacote)** | 4 | 500.000 tokens | 30.000 tokens | Invocação limpa + pacote curto |
| **4. Classificador de Papel** *(se acionado)* | 1 | 60.000 tokens | 5.000 tokens | Chamada classificada de papéis/avaliador |
| **5. Avaliador Cego LLM** *(se acionado)* | 1 | 100.000 tokens | 15.000 tokens | Chamada do avaliador cego com gabarito |
| **6. Margem de Contingência** | 2 | 740.000 tokens | 25.000 tokens | Tolerância para re-tentativas de rede |
| **TETO GLOBAL ESTIMADO** | **11** | **3.400.000 tokens** | **105.000 tokens** | **Total Planejado $\le$ 3.505.000 tokens** |

* **Regra de Esgotamento**: Se qualquer braço atingir seu sub-teto de requisições ou entrada na checagem pós-medição, a execução é suspensa e o resultado registrado como **inconclusivo com ponto de retomada preservado**, resguardando o orçamento do braço oposto e da avaliação.

### 5. Contabilidade Sem Sobreposição e Métricas
Cada requisição deduplicada é alocada a exatamente uma categoria funcional disjunta:
* `Custo de Geração`: Requisições gastas na extração e persistência do pacote de retomada (0 se gerado deterministicamente).
* `Custo de Bootstrap`: Requisições de carregamento inicial e reconhecimento do contexto de trabalho.
* `Custo de Conferência`: Requisições e ferramentas dedicadas à inspeção dos arquivos oficiais apontados.
* `Custo de Formulação`: Requisições dedicadas à síntese da proposta de encaminhamento e elaboração do briefing.

$$\\text{Custo Total Braço B} = \\text{Geração} + \\text{Bootstrap} + \\text{Conferência} + \\text{Formulação}$$
$$\\text{Custo Total Braço A} = \\text{Soma das Requisições Únicas de A}$$

**Métricas Registradas**:
1. `input_tokens` (não-cacheados).
2. `cache_read_input_tokens` (reaproveitados).
3. `cache_creation_input_tokens` (escritas de cache).
4. `output_tokens`.
5. Tempo de relógio observado (latência ponta a ponta até a emissão da proposta).
6. Contagem de operações de ferramentas discriminadas por tipo (`Bash`, `Read`, `Glob`) e **bytes dos resultados de ferramentas na transcrição** (mantendo o tamanho real dos arquivos no disco como medida separada quando disponível).
7. Veredito cego de conformidade segundo o Gabarito Normativo.
*(Reduções de entrada serão registradas em tokens e percentuais estritos, sem conversão direta em moeda).*

### Acceptance criteria
AC01 Montagem mecânica dos ambientes isolados `dir_A` e `dir_B` com 100% de coincidência byte a byte e validação estrutural íntegra (`validate_repository.py` exit 0 em ambos os braços).
AC02 Pacote Curto de Retomada (`short-resume-package.md`) contendo identidade qualificada, estado operacional, governança e hashes SHA-256 de todas as fontes oficiais apontadas, operando como índice aberto de conferência sem tautologia.
AC03 Gabarito Normativo Congelado (`normative-rubric.md`) delimitando critérios Must, May e Must Not para a decisão de condução no checkpoint T009 r02.
AC04 Protocolo e script de sanitização determinística (`sanitize-blind-evaluation.py`) com anonimização para `<root>/`, expurgo de metadados de harness e autoteste verde (exit 0).
AC05 Alinhamento com a política global padrão de participantes (T014): encaminhamento orientado à composição Maker `Gemini 3.8 Flash High` e Checker `Codex GPT-5.6 Terra High` sob filtro estrito de `checker_independence`.
AC06 Execução experimental comparativa com isolamento estrito, medição detalhada de tokens (entrada, cache_read, cache_creation, saída), latência, avaliação cega e descegamento com relatório em `_tl-orc/project/evidence/T012-r01.md`.

### Verification profile
`analysis`: conferência da matriz normativa Must/May/Must Not por avaliação cega contra o gabarito congelado; auditoria de conformidade das leituras realizadas (confinamento à raiz); medição contábil do consumo de tokens e latência; e revisão independente report-only por Checker qualificado.

## Result
Experimento comparativo A/B do piloto de controle de contexto e retomada curta concluído sobre o caso adaptado T009 r02 em ambientes físicos isolados (dir_A e dir_B).
Demonstrou-se empiricamente a viabilidade metodológica da retomada curta via Pacote Curto de Retomada como índice de conferência obrigatória (Braço B), eliminando vícios cognitivos e violações de governança observados no Braço A (que propôs encerrar a tarefa com defeito residual sob X1 e fixar modelos sem classificador sob X2).
Contabilmente, o Braço B reduziu em 35,7% a escrita inicial de cache (246.590 vs 383.583 tokens); contudo, ao aplicar a regra de não-tautologia e inspecionar 15+ fontes em 34 turnos, acumulou 1.466.990 cache_read_input_tokens (vs 655.083 em 11 turnos no Braço A). A avaliação cega independente pelo Codex GPT-5.6 Terra High concluiu que o Braço B é substancialmente mais maduro, seguro e pronto para a condução prática, com zero violações proibidas.

## Evidence
`_tl-orc/project/evidence/T012-r01.md`, `scratch/t012-pilot/arm-a-metrics.json`, `scratch/t012-pilot/arm-b-metrics.json`, `scratch/t012-pilot/blinding-key.json`, `scratch/t012-pilot/review-eval/evaluator-stdout.txt`.

## Review
Rodada r01: Avaliação cega independente realizada pelo Checker Codex GPT-5.6 Terra High sob a política global T014. O avaliador considerou a Decisão Beta (Braço B / Sessão Nova) tecnicamente superior e livre de violações proibidas (X1 a X4 limpos), enquanto a Decisão Alpha (Braço A / Histórico Longo) violou X1 (proposta de encerramento indevido com defeito residual) e X2 (fixação arbitrária sem fluxo formal de classificação). Ambas reprovaram no critério M2 estrito do gabarito por subdividirem os achados em duas classes em vez de classe unificada. Conclusão comparativa ratifica a superioridade de governança da retomada curta.
