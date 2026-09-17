# Política de contexto e economia de sessão

Este documento normativo define a política formal de economia de contexto do `tl-orchestrator`,
estruturada sobre classes de informação abstratas, modos de entrega por fase de trabalho e resolução
determinística por método (`native` ou `bmad`).

A disciplina de contexto não visa truncar evidências nem substituir a conferência rigorosa das fontes;
visa eliminar o retrabalho de auditoria repetida de fontes inalteradas, mitigar a amplificação de busca
(*retrieval amplification*) e viabilizar sessões enxutas, verificáveis e seguras.

---

## 1. Classes de informação

A política declara classes lógicas de informação, e nunca caminhos físicos fixos no código:

| Classe | Descrição | Natureza |
| :--- | :--- | :--- |
| `active_unit.spec` | Especificação da unidade executável (intenção, escopo, critérios de aceite e perfil de verificação). | Contratual |
| `authorization.current` | Autorização vigente, estado da coordenação e parâmetros operacionais do despacho. | Coordenação |
| `unresolved_items` | Pendências, action items abertos e limites de revisões anteriores ainda não quitados. | Qualidade |
| `project.constraints` | Regras transversais, catálogo permitido de modelos e restrições do repositório. | Governança |
| `applicable_decisions` | Decisões arquiteturais e operacionais consolidadas relevantes para a unidade. | Arquitetura |
| `dependency_outputs` | Contratos e resultados expostos por unidades precedentes concluídas. | Interface |
| `previous_rounds` | Histórico de tentativas, relatórios de rodadas anteriores e logs de sessões passadas. | Histórico |
| `discussions` | Sínteses de debates e hipóteses exploradas que não geraram decisões consolidadas. | Contextual |
| `raw_logs` | Saídas brutas de testes, compilações, diffs completos e telemetrias de ferramentas. | Operacional |
| `full_architecture` | Visão panorâmica global do sistema e documentação integral do projeto consumidor. | Referência |

---

## 2. Modos de entrega

Cada classe de informação é atribuída a um dos três modos de entrega:

1. **`inline`:** Conteúdo indispensável para a ação imediata do papel. Entregue integralmente no prompt inicial do despacho.
2. **`excerpt`:** Seção específica e delimitada, estritamente verificada por digest SHA-256 canônico, entregue sem o restante do arquivo.
3. **`on_demand`:** Ponteiro contendo caminho (`path`), seletor de seção (`selector`), digest canônico (`digest`) e justificativa de consulta (`reason`). O agente só realiza a leitura caso a decisão factual expressamente exigir.

---

## 3. Matriz de contexto por fase

A matriz abaixo estabelece a entrega padrão para cada uma das cinco fases do ciclo de vida:

| Classe de informação | `planning` | `implementation` | `review` | `rework` | `debate` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `active_unit.spec` | `inline` | `inline` | `inline` | `inline` | `excerpt` |
| `authorization.current` | `inline` | `inline` | `inline` | `inline` | `inline` |
| `unresolved_items` | `excerpt` | `excerpt` | `inline` | `inline` | `excerpt` |
| `project.constraints` | `excerpt` | `excerpt` | `excerpt` | `excerpt` | `inline` |
| `applicable_decisions` | `excerpt` | `excerpt` | `on_demand` | `excerpt` | `inline` |
| `dependency_outputs` | `excerpt` | `on_demand` | `on_demand` | `on_demand` | `on_demand` |
| `previous_rounds` | `on_demand` | `on_demand` | `excerpt` | `excerpt` | `on_demand` |
| `discussions` | `on_demand` | `on_demand` | `on_demand` | `on_demand` | `excerpt` |
| `raw_logs` | `on_demand` | `on_demand` | `on_demand` | `on_demand` | `on_demand` |
| `full_architecture` | `on_demand` | `on_demand` | `on_demand` | `on_demand` | `on_demand` |

---

## 4. Resolução de artefatos por método de trabalho

O resolvedor determinístico mapeia as classes abstratas para os artefatos concretos da árvore,
segundo o método de trabalho (`work_method`) configurado:

### Perfil Native

- `active_unit.spec` $\to$ Arquivo da Task sob `_tl-orc/project/tasks/`, seletor `## Spec`.
- `authorization.current` $\to$ `_tl-orc/project/STATUS.md`, seletor `frontmatter`.
- `unresolved_items` $\to$ Evidência da rodada anterior sob `evidence/`, seletor `## Review record`.
- `project.constraints` $\to$ `_tl-orc/PROJECT.md`, seletor `frontmatter`.
- `applicable_decisions` $\to$ Arquivos individuais em `_tl-orc/project/decisions/`.

### Perfil BMAD

- `active_unit.spec` $\to$ Especificação da story em `spec-<chave>.md`, seletor `### Acceptance criteria`.
- `authorization.current` $\to$ Arquivo de sprint BMAD ou `STATUS.md`, seletor `frontmatter`.
- `unresolved_items` $\to$ Parecer mais recente sob `pareceres/`.
- `project.constraints` $\to$ `_tl-orc/PROJECT.md`, seletor `frontmatter`.
- `applicable_decisions` $\to$ `_tl-orc/project/decisions/` ou arquitetura BMAD.

Áreas cadastradas em `_tl-orc/PROJECT.md` (`## Work Areas`) estendem os prefixos de caminho sem alterar as classes.

---

## 5. Métricas de eficiência de contexto

- **Retrieval Amplification:**
  $$\text{RA} = \frac{\text{bytes efetivamente carregados das fontes}}{\text{bytes das seções efetivamente usadas}}$$
  Uma seção é considerada *usada* se o seu digest canônico constar na lista `sources` da decisão ou resultado emitido.
- **Tool Delivery Ratio:**
  $$\text{TDR} = \frac{\text{bytes entregues ao modelo}}{\text{bytes brutos emitidos pela ferramenta}}$$
  Menor é melhor, condicionado obrigatoriamente à preservação integral das falhas contratuais (*losslessness*).
- **Bootstrap Cost:**
  Contagem de tokens e turnos consumidos desde o início da sessão até o primeiro despacho efetivo.

---

## 6. Confinamento e isolamento de snapshots

1. **Confinamento de leituras (AC16):**
   Toda leitura de arquivos executada pelos agentes durante a sessão deve recair exclusivamente sobre:
   - `inputs`: Fontes e artefatos congelados da unidade ativa.
   - `allowed-support`: Metadados técnicos do repositório (`.git/`), bibliotecas do sistema e arquivos técnicos do harness.
   Qualquer leitura externa a essas classes é registrada em `reads_outside_allowed_set` e aciona violação no ledger de contexto.
2. **Isolamento de árvores arquivadas (AC17):**
   A descoberta operacional automática ignora terminantemente qualquer caminho sob `project/evidence/` ou `evidence/`.
   Snapshots preservados (como os artefatos de T012) constituem dados históricos de auditoria e jamais configuram instrução ou estado ativo.

---

## 7. Teto mecânico de leituras de bootstrap (`bootstrap_on_demand_budget`)

Na retomada em sessão limpa orientada por `resume.json`, o agente reconstrói seu contexto operacional
consumindo as seções `inline` entregues no manifesto e realizando consultas seletivas sob demanda.
Para evitar que o agente reintroduza silenciosamente o histórico completo ou execute leituras exploratórias
desmedidas antes de agir, a política fixa um teto mecânico e verificável:

- **Parâmetro:** `bootstrap_on_demand_budget` (default operacional: `5` leituras `on_demand`),
  configurável na política de contexto ou na especificação da unidade.
- **Métrica contabilizada:** Cada invocação de ferramenta de leitura seletiva (`scripts/read_section.py`
  ou leitura pontual de trecho) executada desde a inicialização da sessão nova até o primeiro despacho
  material ou decisão de coordenação.
- **Semântica fail-closed:**
  Se a contagem de leituras sob demanda de bootstrap exceder o teto alocado (`reads_count > max_budget`),
  o sistema emite `STOP: bootstrap_budget_exceeded`, bloqueando o prosseguimento.
  A continuidade exige justificativa explícita registrada na evidência da rodada ou elevação formal
  do orçamento na política autorizada da unidade.
- **Verificação mecânica:** O utilitário `scripts/resume_generate.py --check-bootstrap-budget <reads> [--max-budget <N>] [--json]`
  permite a validação determinística desse teto em scripts, CI e portões pré-despacho.
