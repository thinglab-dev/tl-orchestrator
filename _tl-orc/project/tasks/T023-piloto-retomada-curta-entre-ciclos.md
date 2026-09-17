id: T023
type: analysis
deliverable: none
standalone: true
method: native
status: done
state_revision: 2
depends_on: [T010, T021]
blocked_by: []
origin: user (2026-09-09, parecer sobre análise de dados de T009/T010; preparação mecânica e composição padrão alinhada em 2026-09-11)
decisions: []
spec_author: orchestrator
spec_revision: 9c64bc99ae8a8e24
rework_round: 14
affects_context: []
content_paths: [_tl-orc/project/tasks/T023-piloto-retomada-curta-entre-ciclos.md, _tl-orc/project/evidence/T023-r01.md]

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
Entregáveis revisáveis da análise: somente `_tl-orc/project/tasks/T023-piloto-retomada-curta-entre-ciclos.md` e o relatório de evidência experimental `_tl-orc/project/evidence/T023-r01.md`.
Arquivos de suporte mecânico fora da distribuição: `_tl-orc/project/evidence/T023-support/r01/` e `scratch/t023-experiment/`. Proibida qualquer escrita ou modificação nos arquivos do pacote distribuído.

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
| **2. Classificador de Papéis (3 papéis)** | 3 | 180.000 tokens | 10.000 tokens | Chamadas classificadas de papéis (experimental, avaliador e advisor) |
| **3. Advisor (Modo Debater)** | 1 | 100.000 tokens | 10.000 tokens | Consulta ao Advisor cross-family pré-congelamento |
| **4. Braço A (Histórico Acumulado)** | 1 | 2.000.000 tokens | 25.000 tokens | Invocação com histórico preservado ou fornecido |
| **5. Braço B (Sessão Nova + Pacote)** | 10 | 500.000 tokens | 30.000 tokens | Invocação limpa + pacote curto e conferência direta de fontes |
| **6. Avaliador Cego LLM** | 1 | 100.000 tokens | 10.000 tokens | Chamada do avaliador cego com gabarito normativo |
| **7. Checker Independente** *(no fechamento)* | 1 | 500.000 tokens | 15.000 tokens | Revisão independente report-only |
| **8. Contingência Operacional** | 1 | 20.000 tokens | 5.000 tokens | Margem reservada fail-closed para contingências |
| **TETO GLOBAL ESTIMADO** | **18** | **3.400.000 tokens** | **105.000 tokens** | **Total Planejado $\le$ 3.505.000 tokens** |

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
AC06 Execução experimental comparativa com isolamento estrito, medição detalhada de tokens (entrada, cache_read, cache_creation, saída), latência, avaliação cega e descegamento com relatório em `_tl-orc/project/evidence/T023-r01.md` e suporte em `_tl-orc/project/evidence/T023-support/r01/`.

### Verification profile
`analysis`: conferência da matriz normativa Must/May/Must Not por avaliação cega contra o gabarito congelado; auditoria de conformidade das leituras realizadas (confinamento à raiz); medição contábil do consumo de tokens e latência; e revisão independente report-only por Checker qualificado.

## Result
Experimento comparativo A/B do piloto de controle de contexto e retomada curta concluído sobre o caso adaptado T009 r02 em ambientes físicos isolados (dir_A e dir_B), com classificação simétrica prévia sob MSC v3 (Codex gpt-5.6-terra/high congelado para ambos os braços) e consulta prévia ao Advisor (Agy gemini-3.1-pro-high/high em modo Debater).
Demonstrou-se empiricamente a superioridade de governança da retomada curta via Pacote Curto de Retomada como índice de conferência obrigatória (Braço B: 100% de conformidade, zero violações proibidas sob M1-M4 e X1-X4), eliminando o vício cognitivo do Braço A (que violou o critério X2 ao fixar modelos no briefing sem Classificador).
Contabilmente, o Braço B demandou 10 requisições (vs 1 no Braço A) para realizar a conferência direta dos 12 hashes no disco, registrando 81,8% de reaproveitamento de cache (356.864 tokens cacheados de 436.372 de entrada) e totalizando 442.519 tokens na sessão, perfeitamente dentro do sub-teto estrito de 10 requisições e do orçamento global de 3.505.000 tokens (sem estouro e com parada ativa fail-closed comprovada).
Todos os 43 artefatos primários de suporte foram preservados sob `_tl-orc/project/evidence/T023-support/r01/` com 100% de verificabilidade de hashes, suíte de testes contrafactuais de fail-closed aprovada e zero ocorrências de caminhos privados ou identificadores locais.

## Evidence
`_tl-orc/project/evidence/T023-r01.md`.

## Review
- **Rodada r01**: Avaliação cega independente realizada pelo Checker Agy gemini-3.1-pro-high (eleito sob checker_independence: required contra a autoria OpenAI das decisões). O avaliador concluiu que a Decisão Beta (Braço B / Sessão Nova) é tecnicamente superior, plenamente conforme (veredicto PASS, M1-M4 atendidos, zero violações de X1-X4) e demonstra maturidade de governança, enquanto a Decisão Alpha (Braço A / Histórico Longo) reprovou (veredicto FAIL) por violação proibida X2 (fixação arbitrária de modelos sem submissão ao Classificador).
- **Rodada r02 (Checker report-only Codex gpt-5.6-terra/high)**: Emitido parecer com changes_requested apontando R5 (reconciliação do orçamento pré-congelado 18/12 e parada fail-closed) e R6 (eliminação de caminhos físicos locais em artefatos de suporte).
- **Rework r02**: Consulta prévia ao Advisor em modo Debater realizada, orçamento formalmente pré-congelado em 18 requisições globais e sub-teto 12 em B, verificação fail-closed ativa incorporada ao script `run_arms.py`, e todos os artefatos de suporte auditados mecanicamente contra caminhos privados (zero ocorrências remanescentes em `T023-support/r01/`).
- **Rodada r03 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com changes_requested apontando:
  - R5 (high): Orçamento não garantido fail-closed por discrepância aritmética (3 classificadores vs 2 declarados; sub-teto de B em 12 totalizando 19 no pior caso; omissão de avaliador/checker na soma global);
  - R6 (high): Persistência de 41 ocorrências de `/private/tmp/...` contendo identificador local de usuário em `arm-a-history.md`, saídas derivadas e literal em script;
  - R7 (high): Falhas de subprocessos podendo prosseguir como sucesso (`proc.returncode != 0` não causava aborto imediato em `run_arms.py` e `run_evaluator.py`, e veredito JSON não era validado antes do descegamento).
- **Rework r03**:
  - R5 sanado: Sub-teto de Arm B calibrado e congelado para 10 requisições (com circuit breaker ativo); total de 18 requisições discriminado e reconciliado formalmente na spec, no manifesto e no script (3 classificações + 1 advisor + 1 Arm A + 10 Arm B + 1 avaliador + 1 checker + 1 contingência = 18);
  - R6 sanado: Sanitização integral e determinística de todos os artefatos com substituição de caminhos físicos por aliases neutros; varredura mecânica (`grep -rn "/private/tmp"` e `grep -rn "albertiano"`) comprovando exatamente 0 ocorrências em todo o diretório de evidências (exit code 1); regenerados `manifest.json` e `MANIFEST.md` com 43 entradas íntegras;
  - R7 sanado: Inclusão de guardas fail-closed com `raise RuntimeError` para qualquer `proc.returncode != 0` em `run_arms.py` e `run_evaluator.py`, e validação estrita do bloco JSON do veredito antes de permitir qualquer descegamento de chaves; criada e executada a suíte contrafactual `test_fail_closed_guarantees.py` cobrindo 8 cenários de falha com 100% de sucesso.
- **Rodada r04 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R5 (high): Limite de Arm B pós-fato na execução, cálculo global omitia contingência na soma em `run_arms.py`, e relatório/docstring continham declarações residuais de B=12 e 42 artefatos;
  - R7 (high): Saídas de subprocessos gravadas antes da checagem de returncode em `run_arms.py` e `run_evaluator.py`; suíte de testes reproduzia condicionais locais sem importar ou invocar os runners reais;
  - R8 (medium): Validação `validate_repository.py` impedida no sandbox restrito do Checker (`codex exec -s read-only`) por falta de diretório temporário gravável fora do workspace.
- **Rework r04**:
  - R5 sanado: Ledger em `calculate_and_verify_global_budget` soma expressamente as 7 parcelas com contingência (3 classificações + 1 advisor + 1 Arm A + 10 Arm B + 1 avaliador + 1 checker + 1 contingência = 18); declarações residuais de B=12 e 42 artefatos expurgadas de `T023-r01.md:9,28,62` e da docstring de `run_arms.py`;
  - R7 sanado: Guarda `proc.returncode != 0` posicionada imediatamente após `subprocess.run` antes de qualquer I/O de escrita em ambos os runners; runners refatorados em funções testáveis (`enforce_sub_budget`, `calculate_and_verify_global_budget`, `validate_and_extract_verdict`, `unblind_verdict`); `test_fail_closed_guarantees.py` refatorado para importar os módulos reais e comprovar ausência de escrita de arquivos e ausência de leitura da chave em falhas;
  - R8 sanado: Atestado formal de execução de `python3 scripts/validate_repository.py` com exit 0 (`OK: 49 package files; JSON, frontmatter, links, export and hashes validated`) em ambiente nativo gravável vinculado ao commit da árvore revisada.
- **Rodada r05 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R5 (high): Declaração contraditória residual de sub-teto $\le$ 12 em `T023-r01.md:105`; limite de B aferido após término e escrita de artefatos de uso; e `calculate_and_verify_global_budget` somando tokens apenas de A+B, excluindo demais fases;
  - R7 (high): Contraprovas de ausência de I/O não falsificáveis em `test_fail_closed_guarantees.py` (diretório de teste divergente de `OUTPUTS_DIR` e teste do avaliador não verificando ausência de arquivos de saída); `run_evaluator.py` gravava `evaluator-briefing.md` antes da checagem de retorno zero.
- **Rework r05**:
  - R5 sanado: Declaração residual em `T023-r01.md:105` corrigida para $\le$ 10; `run_arm` refatorado para executar inspeção de métricas em arquivo temporário e invocar `enforce_sub_budget` ANTES de qualquer escrita permanente de artefatos no diretório de saída (se B exceder 10 requisições, aborta fail-closed e garante zero artefatos persistidos); `calculate_and_verify_global_budget` atualizado para contabilizar e limitar tokens reais e planejados de TODAS as fases (classificação, advisor, braço A, braço B, avaliação, checker e contingência), conferindo tetos globais de requisições e tokens;
  - R7 sanado: `run_arms.py` e `run_evaluator.py` refatorados com diretórios de saída totalmente configuráveis (`outputs_dir` e `eval_dir`); gravação de `evaluator-briefing.md` movida para após a checagem de retorno zero; `test_fail_closed_guarantees.py` atualizado com 9 testes unitários usando `tempfile.TemporaryDirectory()`, comprovando que tanto a falha de subprocesso quanto o estouro de sub-teto em Arm B garantem zero I/O de saída, e adicionando controle positivo de sucesso que comprova a falsificabilidade das asserções de ausência de I/O.
- **Rodada r06 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R5 (high): Sub-teto de B aferido após conclusão do subprocesso sem impedir a 11ª requisição; ledger global só verificado após execução de ambos os braços em `main()`, sem controle na menor unidade interrompível antes de lançá-las;
  - R7 (high): Falta de staging atômico em `run_arm` (`raw_decision_file` fornecido diretamente ao subprocesso antes da guarda e apagado em erro, arriscando saídas preexistentes); runners criavam diretório de destino antes da guarda; testes não cobriam destino inicialmente inexistente nem mock escrevendo em `-o`.
- **Rework r06**:
  - R5 sanado: Criada a classe `ArmTurnController` que monitora tentativas de lançamento e bloqueia preventivamente o despacho da 11ª requisição de Arm B com `RuntimeError` fail-closed; criada a classe `BudgetTracker` que executa checagem de saldo projetado (`check_pre_phase_budget`) ANTES de autorizar o lançamento de cada braço (bloqueando o despacho se o orçamento global for insuficiente); suíte de testes atualizada com contraprovas de bloqueio de lançamento e controle de fluxo;
  - R7 sanado: Implementado isolamento por staging atômico integral em diretório temporário isolado (`tempfile.TemporaryDirectory()`) para todas as saídas (incluindo `-o` em `run_arm`); os diretórios finais de saída NUNCA são criados ou alterados em caso de falha de subprocesso ou violação de sub-teto; arquivos preexistentes nos destinos nunca são modificados ou apagados; adicionados testes comprovando que diretórios inicialmente inexistentes permanecem não-criados e que arquivos preexistentes permanecem intactos.
- **Rodada r07 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R5 (high): `ArmTurnController` chamava `acquire_launch_permission` uma vez antes do subprocesso único de `codex exec` (que pode agrupar 11 ou mais requisições internas); `BudgetTracker` não avaliava tokens antes das fases (`token_cap` não era usado em `check_pre_phase_budget`); e o teste invocava o controlador isoladamente sem vinculá-lo a despachos reais de turnos;
  - R7 rejeitado com evidência comprovada: Staging atômico integral confirmado e aprovado para falhas de subprocesso, sessão e sub-teto;
  - R6 rejeitado com evidência comprovada: Integridade do manifesto (43 entradas conferidas) e zero vazamentos confirmados (grep exit code 1).
- **Rework r07**:
  - R5 sanado:
    1. *BudgetTracker*: `check_pre_phase_budget` atualizado para reservar e validar atomicamente requisições E tokens (`request_cap = 18`, `token_cap = 3505000`) para todas as fases remanescentes (Arm B: 530k tokens/10 reqs; Avaliador: 110k tokens/1 req; Checker: 515k tokens/1 req; Contingência: 25k tokens/1 req), bloqueando fail-closed qualquer fase com saldo projetado insuficiente;
    2. *Despacho por turnos & Delimitação Monolítica*: Implementada a função `execute_decomposed_arm_turns` vinculando a autorização prévia de `acquire_launch_permission` a cada unidade de requisição antes do despacho, com contraprova integrada comprovando que exatamente 10 turnos são despachados e a 11ª chamada é bloqueada antes de ser lançada (`len(dispatched_calls) == 10`); para execuções monolíticas em que a CLI agrupa turnos sem pausa interna, formalizada a parada pós-medição em staging atômico classificando a execução como inconclusiva com ponto de retomada preservado conforme a Seção 4 da spec;
    3. *Suíte de Testes Contrafactuais*: `test_fail_closed_guarantees.py` expandido para 12 testes unitários e contrafactuais, incluindo a prova integrada de bloqueio da 11ª chamada e a validação atômica de reservas de tokens e requisições no `BudgetTracker`.
- **Rodada r08 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R5 (high): O controle por turno em `execute_decomposed_arm_turns` foi implementado, mas `main()` chamava `run_arm("Arm_B", ...)` com um único `codex exec` opaco; assim, a execução monolítica efetiva não impedia preventivamente o 11º turno interno, e a contraprova cobria apenas o helper isolado com dispatcher injetado sem exercitar o caminho de `run_arm()`;
  - Hipótese de tokens rejeitada com evidência comprovada: `BudgetTracker` validou e reservou atomicamente requisições e tokens para todas as fases remanescentes.
- **Rework r08**:
  - R5 sanado:
    1. *Integração Direta em `run_arm`*: `run_arm` refatorado para suportar internamente o modo decomposto (`decomposed=True` ou lista de prompts), invocando `controller.acquire_launch_permission()` antes de cada despacho unitário; `execute_decomposed_arm_turns` passa a ser um alias direto delegando para `run_arm(..., decomposed=True)`; `main(mode="monolithic")` parametrizado;
    2. *Contraprova Integrada Direta sobre `run_arm`*: Teste `test_decomposed_arm_blocks_11th_turn_dispatch_with_integrated_executor` em `test_fail_closed_guarantees.py` atualizado para invocar diretamente `run_arms.run_arm("Arm_B", ..., decomposed=True, turn_dispatcher=mock_dispatcher)`, comprovando via lista de chamadas reais que exatamente 10 requisições são despachadas (`len(dispatched_calls) == 10`), a 11ª chamada é bloqueada antes do despacho e o diretório de destino permanece não-criado;
    3. *Delimitação Rigorosa da Execução Monolítica*: Registrado formalmente no relatório `T023-r01.md`, na spec e na docstring de `run_arms.py` que a execução real dos braços no piloto utilizou a CLI monolítica `codex exec`, a qual não provê interrupção de turnos internos; para esse fluxo, **não se alega prevenção do 11º turno antes do despacho**; em estrita conformidade com a Seção 4 da spec, a regra aplicável é a parada operacional pós-medição em staging atômico: em caso de estouro de sub-teto em Arm B, `enforce_sub_budget` aborta fail-closed e classifica formalmente a execução como **inconclusiva com ponto de retomada preservado**.
- **Rodada r09 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R7 (high): Publicação em `run_arms.py` e `run_evaluator.py` realizada por múltiplos `copy2` sequenciais sem transacionalidade nem rollback; em caso de falha após a primeira cópia, o diretório de destino ficava criado e parcialmente alterado; suíte cobria falhas pré-publicação e sucesso completo, mas não injetava falha de `copy2`;
  - R5 aprovado e hipótese rejeitada com evidência comprovada: R5 foi formalmente aprovado na alternativa monolítica permitida pela Seção 4 sem alegação indevida de prevenção interna; o modo decomposto chama `acquire_launch_permission` antes de cada despacho e a contraprova comprova exatamente dez despachos antes do bloqueio;
  - Hipóteses de integridade de manifesto (43 entradas conferidas) e ausência de vazamento de caminhos privados rejeitadas com evidência comprovada (grep exit code 1).
- **Rework r09**:
  - R7 sanado:
    1. *Publicação Transacional com Rollback Fail-Closed*: Implementada a função `publish_transactionally(file_mappings, target_dir)` em `run_arms.py` e `run_evaluator.py`; em caso de falha durante a cópia dos artefatos: se o diretório de destino não existia previamente, remove completamente o diretório criado (`shutil.rmtree`), deixando-o não-existente; se o diretório de destino já existia previamente, desfaz mutações parciais restaurando arquivos sobrescritos byte a byte a partir de backup temporário e removendo novos arquivos criados, preservando integralmente o estado prévio sem arquivos residuais;
    2. *Contraprovas Contrafactuais de Injeção de Falha de Publicação*: `test_fail_closed_guarantees.py` expandido para 16 testes contrafactuais, incluindo quatro novas provas de injeção de falha após a primeira cópia (em `run_arm` e `run_evaluator`, para destinos inexistentes e preexistentes), comprovando remoção limpa de diretórios recém-criados e restauração byte a byte com conferência de hash SHA-256 de diretórios preexistentes;
    3. *Sincronização e Auditoria*: Atualizados os artefatos de suporte em `_tl-orc/project/evidence/T023-support/r01/` e regenerados `manifest.json` e `MANIFEST.md` com 43 entradas íntegras e zero vazamentos de caminhos privados locais (exit code 1).
- **Rodada r10 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R7 (high): O rollback em `publish_transactionally` suprimia exceções de `unlink`, `rmtree` e `copy2` via `pass`/`ignore_errors=True`, mas declarava conclusão limpa; suíte injetava falha apenas na cópia de publicação e delegava o rollback ao `orig_copy2` sem testar falha durante a própria reversão;
  - R8 (medium, intent_gap, target_role: human): Instrução imperativa pedindo a execução da suíte de testes pelo Checker sob sandbox somente leitura incompatível com criação de arquivos temporários;
  - Hipóteses de integridade de manifesto (43 entradas conferidas com status 0), zero vazamentos de caminhos privados (exit code 1) e aprovação de R5 ratificadas formalmente.
- **Rework r10**:
  - R7 sanado:
    1. *Eliminação de Supressão de Erros de Rollback*: `publish_transactionally` refatorado em `run_arms.py` e `run_evaluator.py` para nunca engolir exceções durante a reversão; `rmtree` agora é executado sem `ignore_errors=True`; todas as falhas de `unlink`, `rmtree` ou restauração `copy2` são capturadas em lista de erros e, havendo qualquer falha, o runner levanta `RuntimeError` reportando inequivocamente `ROLLBACK FAILED / INCOMPLETE` com discriminação do erro, nunca alegando reversão limpa sem confirmação mecânica; além disso, a restauração byte a byte de arquivos preexistentes é validada por hash SHA-256 pós-cópia;
    2. *Contraprovas Contrafactuais de Falha de Rollback*: `test_fail_closed_guarantees.py` expandido de 16 para **22 testes contrafactuais**, adicionando seis novas provas exercitando diretamente falhas durante o rollback: falha de `rmtree` no destino novo, falha de `copy2` na restauração de arquivo preexistente e falha de `unlink` de arquivo recém-criado, em ambos os runners (`run_arm` e `run_evaluator`), comprovando que todas reportam inequivocamente `ROLLBACK FAILED / INCOMPLETE`;
  - R8 sanado:
    1. Removida do briefing de revisão qualquer instrução imperativa para execução de testes pelo Checker em ambiente somente leitura;
    2. Execução nativa da suíte completa de 22 testes realizada em ambiente gravável com 100% de sucesso (`Ran 22 tests in 0.043s - OK`), registrando formalmente o atestado de conformidade vinculado à árvore revisada.
- **Rodada r11 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R9 (high, patch, target_role: maker): O rollback ainda podia apagar arquivos preexistentes fora de `target_outputs`. Com `outputs_dir` inexistente e `raw_decision_file` ou `usage_json_file` apontando para caminho externo preexistente, a publicação o sobrescrevia; se cópia posterior falhasse, o ramo `not target_existed` executava `dst.unlink()` nesse caminho sem verificar nem restaurar o conteúdo anterior;
  - Hipóteses de saneamento de R8 (remoção de instrução imperativa e atestado nativo em ambiente gravável), saneamento da supressão de erros de rollback em R7 nos dois runners (22 testes conferidos), integridade do manifesto (43 entradas conferidas com status 0) e ausência de vazamentos de caminhos privados (exit code 1) ratificadas formalmente.
- **Rework r11**:
  - R9 sanado:
    1. *Rastreamento Individual de Cada Destino em `publish_transactionally`*: `publish_transactionally` refatorado em `run_arms.py` e `run_evaluator.py` para registrar preventivamente em `backups` o estado prévio e hash SHA-256 de **cada destino individualmente**, independentemente de `target_dir` existir previamente e independentemente de o destino residir dentro ou fora de `target_dir`;
    2. *Preservação Estrita e Rollback Universal*: Em caso de falha de publicação, cada destino que já existia previamente é restaurado byte a byte a partir de backup com validação de hash SHA-256 pós-cópia; apenas destinos que não existiam antes de publicação sofrem `unlink()`; se `target_dir` não existia previamente, é removido via `shutil.rmtree()`;
    3. *Contraprovas Contrafactuais Expandidas para 26 Testes*: `test_fail_closed_guarantees.py` expandido de 22 para **26 testes contrafactuais**, adicionando quatro novas provas exercitando especificamente destinos externos preexistentes com falha posterior (`raw_decision_file` e `usage_json_file` externos preexistentes com remoção limpa de diretório alvo inexistente e preservação byte a byte dos arquivos externos), bem como falhas induzidas na restauração de backup desses arquivos externos comprovando que reportam inequivocamente `ROLLBACK FAILED / INCOMPLETE`;
    4. *Sincronização e Auditoria*: Executada sincronização dos artefatos em `_tl-orc/project/evidence/T023-support/r01/`, com revalidação de 0 vazamentos de caminhos privados (exit code 1) e regeneração de `manifest.json` (43 entradas conferidas) e `MANIFEST.md`.
- **Rodada r12 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R10 (high, patch, target_role: maker): O rollback ainda podia declarar reversão limpa sem restaurar um destino preexistente se `backup_file` registrado deixasse de existir ou estivesse inacessível, pois o ramo `if backup_file.exists()` não continha tratamento de erro; um destino sobrescrito podia permanecer alterado enquanto a exceção final alegava conclusão limpa;
  - Hipóteses de saneamento de R9 (rastreamento individual de destinos e 4 contraprovas em destinos externos), integridade do manifesto (43 entradas conferidas com status 0) e ausência de vazamentos de caminhos privados (exit code 1) ratificadas formalmente.
- **Rework r12**:
  - R10 sanado:
    1. *Tratamento Estrito de Backup Ausente ou Inacessível*: `publish_transactionally` refatorado em `run_arms.py` e `run_evaluator.py` para verificar explicitamente a existência de `backup_file`; se `not backup_file.exists()`, adiciona imediatamente erro a `rollback_errors` discriminando que o arquivo de backup está ausente/inacessível para restaurar o destino, resultando em levantamento obrigatório de `ROLLBACK FAILED / INCOMPLETE` e impedindo qualquer alegação indevida de rollback limpo; além disso, adicionada checagem pós-unlink para destinos recém-criados;
    2. *Contraprovas Contrafactuais Expandidas para 30 Testes*: `test_fail_closed_guarantees.py` expandido de 26 para **30 testes contrafactuais**, adicionando quatro novas provas que removem ou tornam indisponíveis os arquivos de backup após a captura e antes da reversão (para destinos externos de decisão, destinos internos com canary/decisão prévia, destinos de briefing no avaliador e destinos externos de usage), comprovando que todas as quatro situações abortam com `ROLLBACK FAILED / INCOMPLETE` e identificam inequivocamente `missing or inaccessible`;
    3. *Sincronização e Auditoria*: Executada sincronização dos artefatos em `_tl-orc/project/evidence/T023-support/r01/`, com revalidação de 0 vazamentos de caminhos privados (exit code 1) e regeneração de `manifest.json` (43 entradas conferidas) e `MANIFEST.md`.
- **Rodada r13 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R11 (high, patch, target_role: maker): A consulta `backup_file.exists()` ocorria fora de `try/except`; se a inacessibilidade do backup fizer `exists()` lançar `OSError`/`PermissionError`, a exceção escapava do rollback, interrompia a reversão dos demais destinos e não emitia o `RuntimeError` obrigatório com `ROLLBACK FAILED / INCOMPLETE`. Exigido: capturar erros de `exists()/stat` do backup, acumulá-los em `rollback_errors`, continuar a reversão dos demais destinos antes de levantar `ROLLBACK FAILED / INCOMPLETE` e adicionar contraprovas nos runners reais que simulem `PermissionError`/`OSError` na consulta do backup e confirmem a tentativa de cleanup restante;
  - Hipóteses de saneamento de R10 (tratamento estrito de backup ausente ou inacessível e 4 contraprovas), integridade do manifesto (43 entradas conferidas com status 0) e ausência de vazamentos de caminhos privados (exit code 1) ratificadas formalmente.
- **Rework r13**:
  - R11 sanado:
    1. *Captura e Resiliência de `exists()/stat` no Rollback*: `publish_transactionally` refatorado em `run_arms.py` e `run_evaluator.py` para envolver a verificação `backup_file.exists()` em bloco `try/except Exception as stat_err:`. Qualquer erro de I/O (`OSError`, `PermissionError`) é capturado e acumulado em `rollback_errors` (`Failed to check existence/stat of backup file...`), executando `continue` para prosseguir com a reversão de todos os demais destinos antes de levantar o `RuntimeError` com `ROLLBACK FAILED / INCOMPLETE`; de forma análoga, verificações de `dst.exists()` e `target_dir.exists()` durante cleanup pós-unlink e pós-rmtree foram protegidas por `try/except` acumulando em `rollback_errors`;
    2. *Contraprovas Contrafactuais Expandidas para 32 Testes*: `test_fail_closed_guarantees.py` expandido de 30 para **32 testes contrafactuais**, adicionando duas novas provas contrafactuais: `test_run_arm_publication_failure_backup_exists_permission_error_reports_incomplete_rollback_and_continues_cleanup` (simulando `PermissionError` na consulta de `backup_file.exists()`, confirmando captura, acúmulo de erro, continuidade do cleanup com remoção de `test_out_dir` e reporte estrito de `ROLLBACK FAILED / INCOMPLETE`) e `test_run_evaluator_publication_failure_backup_exists_oserror_reports_incomplete_rollback` (simulando `OSError` na consulta de `backup_file.exists()` no avaliador, confirmando captura e reporte estrito de `ROLLBACK FAILED / INCOMPLETE`);
    3. *Sincronização e Auditoria*: Executada sincronização dos artefatos em `_tl-orc/project/evidence/T023-support/r01/`, com revalidação de 0 vazamentos de caminhos privados (exit code 1) e regeneração de `manifest.json` (43 entradas conferidas) e `MANIFEST.md`.
- **Rodada r14 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer com `changes_requested` apontando:
  - R12 (high, patch, target_role: maker): A contraprova do avaliador para erro de stat do backup não demonstrava a continuidade do cleanup exigida por R11; embora `run_evaluation` publique quatro destinos, não havia segundo destino/canário nem asserção de remoção ou restauração após a falha de `backup_file.exists()`, de modo que um mutante que interrompesse o loop sem `continue` ainda satisfaria o teste. Exigido: estender o teste do avaliador com um destino subsequente observável e afirmar sua reversão/remoção após o `OSError` de stat, de modo que a ausência do `continue` no rollback faça a contraprova falhar;
  - Hipóteses de que a implementação deixa exceções de stat escaparem (aprovada resiliência de `try/except` e acúmulo de `rollback_errors` em ambos os runners), integridade do manifesto (43 entradas conferidas com status 0) e ausência de vazamentos de caminhos privados (exit code 1) ratificadas formalmente.
- **Rework r14**:
  - R12 sanado:
    1. *Contraprovas com Destinos Subsequentes Observáveis e Falsificabilidade Comprovada*: Em `test_fail_closed_guarantees.py`, os testes contrafactuais de erro de stat de backup nos dois runners foram estendidos com destinos subsequentes observáveis:
       - `test_run_evaluator_publication_failure_backup_exists_oserror_reports_incomplete_rollback_and_continues_cleanup`: configurado com destino prévio 1 (`evaluator-briefing.md`, cujo stat de backup falha com `OSError`), destino subsequente observável 2 preexistente (`evaluator-stdout.txt`), destino 3 recém-criado antes da falha (`evaluator-stderr.txt`) e canário intacto. Comprovado que: o destino 2 subsequente foi restaurado byte a byte de seu backup (`assert stdout == "prior stdout content"` e hash SHA-256 idêntico), o destino 3 recém-criado foi desfeito (`assertFalse(stderr.exists())`), o canário permaneceu intacto e o rollback incompleto foi reportado. Falsificabilidade comprovada contra mutante com `break`, o qual falha deterministicamente;
       - `test_run_arm_publication_failure_backup_exists_permission_error_reports_incomplete_rollback_and_continues_cleanup`: estendido similarmente com destino subsequente observável preexistente (`ext_usage_file`), comprovando sua restauração byte a byte de backup com conferência de hash SHA-256 e remoção limpa do diretório temporário criado;
    2. *Sincronização e Auditoria*: Executada sincronização dos artefatos em `_tl-orc/project/evidence/T023-support/r01/`, com revalidação de 0 vazamentos de caminhos privados (exit code 1) e regeneração de `manifest.json` (43 entradas conferidas) e `MANIFEST.md`.
- **Rodada r15 (Checker report-only Codex gpt-5.6-terra/high)**: Parecer **APPROVED** com 0 action items:
  - R12 plenamente sanado: as contraprovas tornam observável a continuidade do rollback após erro de stat (`test_fail_closed_guarantees.py:1728-1832` restaura `ext_usage_file` e remove `test_out_dir`; `:1834-1927` restaura `evaluator-stdout.txt`, remove `evaluator-stderr.txt` e preserva o canário; em ambos os runners, `backup_file.exists()` é capturado, registrado e seguido de `continue` em `run_arms.py:254-260` e `run_evaluator.py:228-234`; mutar para `break` impede as asserções dos destinos subsequentes comprovando falsificabilidade);
  - Integridade do manifesto confirmada (43 entradas para 43 artefatos primários, todas com bytes e SHA-256 recomputados sem divergência; `MANIFEST.md` contém 43 linhas);
  - Ausência de caminhos privados confirmada (0 ocorrências de `/private/tmp` e do identificador local em `T023-r01.md` e `T023-support/r01/`);
  - Zero alterações no pacote distribuído (`prompts/`, `schemas/`, `docs/`, `distribution-manifest.json`). Entrega formalmente aprovada.
