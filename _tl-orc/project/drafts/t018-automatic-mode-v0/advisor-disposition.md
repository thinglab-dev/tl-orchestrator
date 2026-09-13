# Registro de Disposição dos Achados do Advisor — Modo Automático (T018)

**Data da Consulta:** 2026-09-12  
**Harness / Modelo do Advisor:** Claude (`claude-3-7-sonnet-20250219` / `sonnet` em esforço `high`, Anthropic)  
**Independência:** `full_cross_family` contra `challenged_author_families: [openai, google]`  
**Veredito Original:** `adjust` (Confiança: `high`, `debate_required: false`)  
**Decisão Humana / Mantenedor:** Disposição integral de todos os 7 achados e evidências faltantes; sem necessidade de Debate formal ou de segundo Advisor. Spec autorizada para formalização em `ready` após ajustes.

---

## 1. Disposição dos Achados (`findings`)

### Achado 1 — Reserva de Orçamento por Ciclo de Unidade
- **Diagnóstico do Advisor:** O orçamento observável (`model_call_budget`) não reservava chamadas para `Classifier + Checker` antes de autorizar o Maker a começar. Se o orçamento se esgotasse após o Maker, um commit local não verificado ficaria abandonado na árvore (`local_commit: true`), gerando um estado pior do que ter interrompido antes.
- **Disposição Ratificada e Fortalecida:**
  * Aceito e fortalecido: a admissão de uma unidade exige garantia de orçamento mínimo para cobrir todo o caminho obrigatório até a revisão independente, incluindo os Classifiers obrigatórios por fase.
  * Antes de iniciar uma unidade nova: reserva mandatória mínima de `Classifier implementation + Maker + Classifier review + Checker` (4 chamadas a modelos). Se Planner ou Advisor forem exigidos no ponto de admissão, entram também na reserva mandatória.
  * Antes de despachar o Maker (com Classifier de impl já consumido): devem restar pelo menos `Maker + Classifier review + Checker` (3 chamadas).
  * Antes de iniciar um retrabalho (*rework*): exige saldo para um ciclo completo de `Classifier rework + Maker + Classifier review + Checker` (4 chamadas).
  * Se a reserva mínima não estiver disponível, a execução interrompe imediatamente com `STOP: insufficient_budget_for_unit_verification`.

### Achado 2 — Revalidação Pré-Freeze contra Drift durante Espera Humana
- **Diagnóstico do Advisor:** Entre `PROPOSE` e a autorização humana em `WAIT_AUTHORIZATION`, pode transcorrer tempo significativo (regime de tolerância a esperas de T013). Uma unidade proposta pode sofrer alteração na árvore ou drift de especificação/dependência, sendo congelada com um digest desatualizado sem validação.
- **Disposição Ratificada:**
  * Aceito integralmente: introdução formal do estado intermediário `PREFREEZE_REVALIDATE` imediatamente antes de `FREEZE_BATCH`.
  * Recalculam-se obrigatoriamente: revisões de unidade, specs, dependências, `scope_digest` e efeitos permitidos.
  * Qualquer divergência detectada invalida sumariamente a proposta anterior: é terminantemente proibido adaptar o lote silenciosamente. O sistema retorna ao estado `PROPOSE` com uma proposta atualizada para nova apreciação humana.

### Achado 3 — Revalidação de Árvore e Coordenador em Lotes Longos
- **Diagnóstico do Advisor:** O liveness guard de T013 opera apenas sobre travamento mecânico de subprocessos em uma chamada isolada, não detectando mutações externas ou perda de lock de coordenador ao longo de um lote longo com múltiplas unidades autônomas.
- **Disposição Ratificada com Precisão Técnica:**
  * Aceito com especificação estrita: o invariante não é genericamente `git status clean`, mas `tree_state == expected_checkpoint`.
  * Quando `local_commit: true`, `expected_checkpoint` corresponde a `HEAD == expected_commit` com árvore de trabalho limpa. Se commits locais não forem autorizados, exige-se o digest explícito do estado de arquivos esperado.
  * Antes de admitir cada nova unidade no loop `EXECUTE`: revalidam-se o coordenador (`STATUS.md`), a revisão da unidade e o estado da árvore contra o checkpoint esperado. Havendo divergência, interrompe-se com `STOP: unexpected_revision_drift` ou `STOP: coordinator_conflict`.

### Achado 4 — Semântica de Aprovação Humana Parcial
- **Diagnóstico do Advisor:** O rascunho previa apenas aceitação integral ("aprovando integralmente a proposta"), deixando ambíguo se a aprovação de um subconjunto de unidades gerava novo `PROPOSE` ou se era simplesmente rejeitada.
- **Disposição Ratificada:**
  * Aceita e fixada em semântica conservadora: aprovação parcial **nunca** filtra diretamente o lote no freeze.
  * Caso o usuário aprove apenas um subconjunto (ex.: "aprovar T018 e T019, excluir T020"), o Orquestrador gera obrigatoriamente um novo ciclo `PROPOSE` contendo estritamente as unidades aprovadas, recalculando dependências, orçamentos, boundaries de integração e digest da proposta para nova confirmação explícita.
  * Apenas uma proposta integralmente aprovada pelo usuário avança para `PREFREEZE_REVALIDATE → FREEZE_BATCH`.

### Achado 5 — Simetria da Condição `bad_spec_or_intent_gap`
- **Diagnóstico do Advisor:** O rascunho deixava implícito se `bad_spec_or_intent_gap` operava apenas como achado do Checker pós-implementação ou se também impedia o avanço ao Maker caso apontado pelo Classifier.
- **Disposição Ratificada:**
  * Aceita integralmente: a condição é simétrica.
  * Se o Classifier da fase ou qualquer verificação estática pré-Maker revelar incerteza material insolúvel, contradição de autoridade ou lacuna de intenção na especificação, a unidade interrompe imediatamente (`STOP: bad_spec_or_intent_gap`) antes de despachar o Maker, evitando queima desnecessária de chamadas.

### Achado 6 — Desqualificação da Alternativa C (Runtime-only)
- **Diagnóstico do Advisor:** A Alternativa C (lote mantido apenas em memória) viola frontalmente o requisito 1.1.6 ("recuperação durável, auditável e segura após interrupção") e não deveria figurar como alternativa viável.
- **Disposição Ratificada:**
  * Aceita formalmente: a Alternativa C é rejeitada por incompatibilidade arquitetural com a garantia de recuperação auditável e durabilidade. Ela fica registrada na documentação de decisões do projeto exclusivamente como alternativa avaliada e descartada.

### Achado 7 — Decisão de Persistência: Adoção do Híbrido A+B
- **Diagnóstico do Advisor:** A Alternativa A pura cria risco de split-brain com `STATUS.md`. A Alternativa B pura infla a leitura de `STATUS.md` em toda ativação, violando a economia de contexto de T015. O Advisor recomendou uma solução híbrida: snapshot imutável em arquivo dedicado de batch, com apenas um ponteiro enxuto de uma linha em `STATUS.md`.
- **Disposição Ratificada:**
  * Adotada integralmente a solução híbrida:
    - **Fonte de verdade do lote:** Novo arquivo dedicado `_tl-orc/project/batches/Bnnn.md`, contendo autoridade imutável, snapshot de unidades, orçamentos e seções mutáveis de execução;
    - **Projeção e Coordenação:** `_tl-orc/project/STATUS.md` mantém apenas o ponteiro leve (`active_batch: Bnnn`, `batch_status: in_progress`, `next_batch_id: N`) e preserva o mutex de coordenação da árvore.
    - **Regra de resolução:** Se houver divergência entre o arquivo do lote e o ponteiro em `STATUS.md`, a autoridade é `Bnnn.md`; `STATUS.md` é reconciliado como projeção.

---

## 2. Disposição das Evidências Faltantes (`missing_evidence`)

1. **Contabilidade de Chamadas por Write-Ahead Lógico (sem ilusão de transação distribuída):**
   * Em vez de prometer garantias transacionais complexas incompatíveis com scripts locais, adota-se **serialização pelo coordenador com reserva write-ahead**:
     $$\text{verificar saldo} \to \text{reservar slots no batch} \to \text{gravar } pending\_call \to \text{despachar modelo} \to \text{observar retorno} \to \text{converter reserved} \to \text{consumed} \to \text{limpar } pending\_call$$
   * Na retomada de interrupção: se `pending_call` existir, checa-se se houve evidência inequívoca de despacho; se ambíguo, contabiliza-se conservadoramente como `consumed` e interrompe-se (`STOP`). Isso garante matematicamente que uma falha de harness nunca resulte em exceder o orçamento silenciosamente.
2. **Tratamento de Aprovação Parcial:** Formalizado como retorno a `PROPOSE` com recálculo de digest.
3. **Interação com Contadores de `STATUS.md`:** `STATUS.md` recebe o contador `next_batch_id` para numeração sequencial determinística dos lotes (`B001`, `B002`, ...).

---

## 3. Impacto Normativo na Autoria Material de T018

Conforme o contrato de autoria estrita do papel Advisor (AC11 de T017):
- Como as contribuições conceituais e estruturais do parecer do Advisor Anthropic foram substantivamente incorporadas à especificação arquitetural final de T018, a autoria material acumulada da especificação de T018 é oficialmente:
  ```yaml
  effective_authors:
    - openai
    - google
    - anthropic
  ```
- **Consequência de Independência para T018:**
  No catálogo atual com três famílias de modelos (OpenAI, Google e Anthropic), o conjunto de famílias alternativas elegíveis para o Checker de T018 é vazio ($\text{disponíveis} \setminus \{\text{openai}, \text{google}, \text{anthropic}\} = \emptyset$).
  Portanto, para a revisão da entrega de T018:
  * Sob `checker_independence: preferred`, é obrigatória a admissão de fallback degradado de mesma família em sessão limpa (`same_family_fresh_session`), com o devido registro formal na evidência.
  * A política `checker_independence: required` está vedada para a entrega de T018, pois bloquearia a conclusão da tarefa por ausência de uma quarta família de IA.
