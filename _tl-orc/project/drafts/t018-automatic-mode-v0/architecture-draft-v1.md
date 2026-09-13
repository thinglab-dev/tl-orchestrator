# Arquitetura v1 — Modo Automático (T018)
## Execução Autônoma de Lote Finito Autorizado, Recuperação e Fronteiras

**Status do Artefato:** Especificação arquitetural consolidada pós-desafio do Advisor e ratificação com refinamentos pelo mantenedor.  
**Autoria Material Acumulada da Arquitetura:**
- `openai`: Concepção original da máquina de estados, autorização em duas fases, orçamentos observáveis e salvaguardas operacionais;
- `google`: Formalização dos contratos normativos, salvaguardas invariantes, integração aos protocolos T013–T017 e modelagem de admissão;
- `anthropic`: Desafio consultivo do primeiro Advisor independente, identificação de 7 achados críticos e desenho da persistência híbrida, reserva dinâmica de verificação por unidade, validação pré-freeze e write-ahead de chamadas.
**`effective_authors`:** `[openai, google, anthropic]`

---

## 1. Objetivo e Fronteira de Autoridade

### 1.1 Objetivo Central
Permitir a execução autônoma de um **lote finito e explicitamente autorizado** de unidades já conhecidas do projeto, preservando integralmente:
1. **Autoridade humana exclusiva** sobre escopo, orçamento, inclusão de unidades e efeitos externos;
2. **Escopo estritamente congelado** no momento do freeze do lote;
3. **Orçamento observável e garantido**, impedindo a criação de implementações que não possuam saldo para revisão independente;
4. **Independência rigorosa dos revisores** (Checker e Advisor conforme os contratos de T014 e T017);
5. **Verificação econômica contínua** (testes direcionados intragrupo e portões canônicos completos nas fronteiras maiores — T016);
6. **Recuperação durável, auditável e segura** a partir de persistência em disco após interrupção.

### 1.2 Natureza do Sistema e Não-Objetivos (Anti-Patterns Expressamente Vedados)
- **T018 não cria daemon, transação distribuída ou engine autônomo persistente**. O Modo Automático é um protocolo durável conduzido pelo Orchestrator/harness existente. O *write-ahead* é uma disciplina documental serializada pelo `coordinator`, não uma promessa de atomicidade de banco de dados.
- **Não** criar agentes indefinidamente autônomos ou auto-direcionados;
- **Não** percorrer backlog de forma contínua ou descontrolada;
- **Não** criar ou formalizar novas Tasks espontaneamente;
- **Não** auto-autorizar escopo, orçamento, efeitos ou exceções;
- **Não** manter serviços em segundo plano, daemons permanentes ou loops de polling contínuo;
- **Não** presumir nem executar `git push`, PR, merge remoto, tags git ou releases sem instrução humana explícita prévia.

---

## 2. Máquina de Estados do Modo Automático

```text
IDLE
  ↓ comando explícito do usuário: "iniciar modo automático"
DISCOVER                  # read-only: inspeção de unidades candidatas existentes
  ↓
PROPOSE                   # read-only: geração da proposta formal de lote
  ↓
WAIT_AUTHORIZATION        # bloqueio síncrono aguardando deliberação humana
  ├── rejeição → IDLE
  ├── aprovação parcial → PROPOSE revisado (novo ciclo com subconjunto)
  └── aprovação integral
          ↓
PREFREEZE_REVALIDATE      # revalidação síncrona de drifts entre proposta e autorização
  ├── drift detectado → PROPOSE revisado (invalida proposta anterior)
  └── integridade confirmada
          ↓
FREEZE_BATCH              # materialização imutável do snapshot do lote em batches/Bnnn.md
          ↓
EXECUTE                   # loop sequencial de execução por unidade com admission gate
          ↓
CLOSE                     # fechamento do lote com relatório terminal ao usuário

Saídas Excepcionais (Terminais ou com Ponto de Retomada):
BLOCKED | STOPPED | FAILED | CANCELLED
```

### 2.1 Invariante Fundamental de Autorização
```text
"iniciar modo automático" ≠ autorização para executar
```
O comando inicial do usuário autoriza **única e exclusivamente** a fase de leitura `DISCOVER → PROPOSE`.  
Nenhuma modificação de código, criação de commit, mutação de arquivo ou despacho de agentes de implementação pode ocorrer antes de uma resposta humana formal que aprove a proposta apresentada.

### 2.2 Semântica Estrita de Aprovação Parcial
Caso o usuário responda aprovando apenas uma parte das unidades propostas (ex.: *"execute T018 e T019, mas deixe T020 de fora"*):
- A aprovação parcial **nunca filtra diretamente o lote no momento do freeze**;
- O Orquestrador gera obrigatoriamente um novo ciclo `PROPOSE` contendo estritamente o subconjunto aprovado;
- Recalculam-se dependências, orçamentos, boundaries de integração e o novo `proposal_digest`;
- A nova proposta é submetida ao usuário para confirmação formal; somente uma proposta integralmente aceita pode avançar.

### 2.3 Revalidação Pré-Freeze (`PREFREEZE_REVALIDATE`)
Entre a emissão de `PROPOSE` e a resposta do usuário em `WAIT_AUTHORIZATION`, pode ocorrer drift na árvore ou alterações manuais em arquivos. Imediatamente antes de materializar o lote em disco:
- Recalculam-se: revisões das unidades, `spec_revision` de cada task, grafo de dependências, `scope_digest` e efeitos autorizados;
- Se houver **qualquer divergência**: a proposta anterior é considerada sumariamente inválida. O sistema **não adapta silenciosamente** o lote; retorna ao estado `PROPOSE` com a proposta atualizada;
- Se todos os digests conferirem perfeitamente: o lote avança para `FREEZE_BATCH`.

---

## 3. Persistência Durável do Lote: Modelo Híbrido Adotado

Desqualifica-se e rejeita-se formalmente a Alternativa C (*runtime-only* em memória) por violar a durabilidade e a rastreabilidade exigidas pelo método.

Adota-se a arquitetura híbrida recomendada pelo Advisor e ratificada pelo mantenedor:
1. **Fonte de Verdade do Lote:** Arquivo dedicado `_tl-orc/project/batches/Bnnn.md`.
2. **Projeção e Coordenação da Árvore:** Ponteiro enxuto de uma linha em `_tl-orc/project/STATUS.md`.

### 3.1 Alvo e Estrutura de `schemas/batch.schema.json`
O schema `schemas/batch.schema.json` valida o **envelope estruturado / frontmatter YAML** de `_tl-orc/project/batches/Bnnn.md`.  
O arquivo possui duas naturezas bem distintas:
- Uma seção **imutável** gravada no freeze contendo autoridade, escopo congelado, limites e o `immutable_digest`;
- Seções **mutáveis** de acompanhamento, orçamentos e execução sequencial (`status`, `budget consumed/reserved`, `current_unit`, `pending_call`, checkpoints).
- O progresso da execução **não pode alterar retroativamente** a autoridade ou o escopo congelado.

```yaml
id: B001
status: in_progress
batch_revision: 1

authorization:
  proposal_id: "prop-20260912-001"
  proposal_digest: "sha256:..."
  authority_source: "explicit_user_authorization"
  authorized_at: "2026-09-12T16:00:00Z"
  permitted_effects:
    local_write: true
    local_commit: true
    local_merge: false
    pull_request: false
    push: false
    tag: false
    release: false
  continue_independent_after_block: false

frozen_scope:
  units:
    - work_ref: "T018"
      revision: 1
      spec_revision: "..."
      integration_group: "group-native"
      dependencies: []
    - work_ref: "T019"
      revision: 1
      spec_revision: "..."
      integration_group: "group-native"
      dependencies: ["T018"]
  integration_groups:
    group-native: ["T018", "T019"]
  major_boundaries:
    - from: "group-native"
      to: "batch_closure"
      gate: "python3 scripts/validate_repository.py"
  stop_conditions:
    - authority_missing_or_ambiguous
    - scope_expansion
    - new_work_outside_frozen_batch
    - model_call_budget_exhausted
    - rework_limit_exhausted
    - insufficient_budget_for_unit_verification
    - required_checker_independence_unavailable
    - required_advisor_independence_unavailable
    - advisor_verdict_stop
    - advisor_verdict_debate
    - bad_spec_or_intent_gap
    - canonical_full_gate_failure
    - coordinator_conflict
    - unexpected_tree_state
    - unexpected_revision_drift
    - external_effect_not_authorized
    - unrecoverable_harness_failure
    - dependency_block
  immutable_digest: "sha256:..."

budget:
  max_model_calls: 24
  consumed_model_calls: 0
  reserved_model_calls: 0
  max_rework_rounds_per_unit: 2
  max_advisor_calls: 2
  consumed_advisor_calls: 0
  pending_call: null

execution:
  current_unit: "T018"
  current_phase: "implementation"
  current_round: 0
  expected_tree_checkpoint: "4775c6b39c954da49aa40562afeea7e3eafad390"
  completed_units: []
  stop_reason: null
```

### 3.2 Projeção em `_tl-orc/project/STATUS.md`
`STATUS.md` permanece curto, rápido de ler e dono do lock de coordenação da árvore:
```yaml
active_batch: B001
batch_status: in_progress
next_batch_id: 2
```
- **Regra de resolução de conflito:** Se houver qualquer divergência entre `STATUS.md` e `Bnnn.md`, a autoridade sobre o lote é o arquivo do lote `Bnnn.md`. O Orquestrador relê o batch e reconcilia a projeção em `STATUS.md`.

---

## 4. Contabilidade de Chamadas por Write-Ahead Lógico

O método não finge transacionalidade distribuída inexistente. A contabilidade é garantida por **serialização pelo coordenador e write-ahead de reserva**:

```text
1. Verificar saldo disponível no lote
2. Reservar slots obrigatórios (reserved_model_calls += N)
3. Gravar pending_call no Bnnn.md com call_id e payload esperado
4. Persistir estado do lote em disco
5. Despachar a chamada ao modelo
6. Observar o receipt/resultado estruturado
7. Converter: reserved -= 1, consumed += 1
8. Limpar pending_call no Bnnn.md
9. Persistir estado atualizado
```

### 4.1 Recuperação de Crash ou Interrupção
Ao reiniciar a execução do lote após falha de processo ou sessão:
```text
pending_call existe no Bnnn.md?
 ├── NÃO → retoma a partir do último checkpoint confirmado
 └── SIM → verificar se há evidência inequívoca de despacho:
             ├── SIM (recibo/log confirma saída) → contabilizar como consumed e prosseguir
             ├── NÃO (despacho comprovadamente não ocorreu) → liberar reserva e prosseguir
             └── AMBÍGUO → contabilizar conservadoramente como consumed e STOP imediato
```
Essa regra impede que falhas ou interrupções resultem em estouro acidental de orçamento.

---

## 5. Admissão e Loop de Execução por Unidade (`EXECUTE`)

### 5.1 Admission Gate por Unidade
Antes de admitir qualquer unidade para execução no lote:
```text
1. authority ainda válida e inalterada
2. batch membership confirmado (unidade presente no snapshot congelado)
3. revision e spec_revision confirmadas sem drift
4. dependencies da unidade totalmente satisfeitas (status == done)
5. coordinator válido em STATUS.md
6. tree_state == expected_checkpoint (HEAD esperado e árvore limpa)
7. efeitos necessários contidos em permitted_effects
8. mandatory call reserve dinamicamente disponível no orçamento
```

### 5.2 Cálculo Dinâmico da Reserva Mandatória de Orçamento
A reserva de orçamento **não é um número fixo universal**, mas uma função dinâmica do caminho obrigatório restante:
```text
required_call_reserve =
  todas as chamadas obrigatórias ainda não consumidas
  do checkpoint atual
  até o Checker independente
```
- A admissão de uma unidade exige garantia de orçamento para cobrir todo o caminho até a revisão independente, incluindo Classifiers obrigatórios de cada fase, Maker, Checker e, quando já exigidos pela política ou contexto, Planner ou Advisor.
- Exemplos no fluxo comum (não normativos como constantes):
  * Unidade nova simples típica: $\ge 4$ chamadas (`Classifier impl + Maker + Classifier rev + Checker`); caso Advisor ou Planner entrem no caminho, a reserva sobe proporcionalmente.
  * Antes de despachar o Maker (Classifier já consumido): $\ge 3$ chamadas (`Maker + Classifier rev + Checker`).
  * Antes de retrabalho (*rework*): só inicia se houver saldo para todo o ciclo obrigatório restante até o re-review ($\ge 4$ chamadas para `Classifier rework + Maker + Classifier rev + Checker`).
- Se o saldo restante for inferior a `required_call_reserve`:
  $$\text{STOP: } insufficient\_budget\_for\_unit\_verification$$

### 5.3 Loop Interno e Aplicação de T016 dentro do Lote
Um único lote pode conter unidades de diferentes grupos de integração. A cadência de verificação T016 aplica-se rigorosamente:
```text
Admission Gate PASS
        ↓
Classifier da fase (obrigatório, perfil fixo, sem auto-escolha de modelo/effort)
        ↓
bad_spec_or_intent_gap ou incerteza material insolúvel?
 ├── SIM → STOP imediato (simétrico: interrompe antes do Maker)
 └── NÃO → continua
        ↓
Advisor? ─── SOMENTE se gatilho objetivo de T017 estiver presente (não recursivo, debita do budget)
        ↓
Planner? ─── SOMENTE se autorizado no lote
        ↓
Verificação de reserva pós-Classificação (saldo ≥ chamadas restantes até Checker?)
 ├── NÃO → STOP: insufficient_budget_for_unit_verification
 └── SIM → continua
        ↓
Maker (implementação estritamente contida em content_paths)
        ↓
Targeted Verification (T016 — suíte direcionada)
        ↓
Classifier de Review
        ↓
Checker Independente (T014 / T017 — fresh session, report-only)
        ↓
approved?
 ├── SIM → marca unidade done, atualiza checkpoint de árvore
 └── NÃO → action items do Checker:
             ├── target_role == maker AND dentro de spec/content_paths AND saldo ≥ ciclo de rework → Rework
             └── bad_spec | intent_gap | target_role == human | expansão de escopo | saldo insuficiente → STOP
        ↓
mudou integration_group?
 ├── NÃO → avança para próxima unidade do mesmo grupo
 └── SIM → executa canonical_full_gate oficial na fronteira do grupo que encerra:
              ├── PASS → avança para a primeira unidade do próximo grupo
              └── FAIL → STOP: canonical_full_gate_failure
```

---

## 6. Condições Formais de Parada (*Stop Conditions*)

O Modo Automático deve interromper a execução (`STOP`) e devolver o controle imediato ao usuário quando qualquer uma das 18 condições for acionada:

1. `authority_missing_or_ambiguous`: ausência de comando formal explícito.
2. `scope_expansion`: tentativa de escrita fora dos `content_paths` congelados.
3. `new_work_outside_frozen_batch`: necessidade de Task nova não presente no snapshot.
4. `model_call_budget_exhausted`: orçamento de chamadas do lote esgotado.
5. `rework_limit_exhausted`: esgotamento do número de rodadas de retrabalho da unidade.
6. `insufficient_budget_for_unit_verification`: saldo restante inferior a `required_call_reserve`.
7. `required_checker_independence_unavailable`: indisponibilidade de família independente sob política `required`.
8. `required_advisor_independence_unavailable`: indisponibilidade de consultor independente sob política `required`.
9. `advisor_verdict_stop`: parecer de parada emitido pelo Advisor.
10. `advisor_verdict_debate` (ou `debate_required: true`): necessidade de deliberação sem autorização prévia de debate.
11. `bad_spec_or_intent_gap`: especificação inconsistente ou lacuna de intenção levantada por Classifier ou Checker (simétrico).
12. `canonical_full_gate_failure`: falha de portão canônico em fronteira de grupo ou fechamento.
13. `coordinator_conflict`: divergência de coordenador da árvore.
14. `unexpected_tree_state`: árvore de trabalho não condiz com `expected_tree_checkpoint`.
15. `unexpected_revision_drift`: divergência de revisão em relação ao snapshot congelado.
16. `external_effect_not_authorized`: tentativa de invocar push, PR, merge, tag ou rede.
17. `unrecoverable_harness_failure`: falha persistente de infraestrutura de harness.
18. `dependency_block`: bloqueio de dependência de unidade no lote.
    - O padrão é `continue_independent_after_block: false` (interrompe no primeiro bloqueio). Continuidade sobre unidades independentes exige autorização explícita.

---

## 7. Fechamento do Lote (`CLOSE`)

Um lote encerra-se quando:
1. Todas as unidades terminais do lote atingem `status: done`;
2. O portão canônico de integração de fronteira do último grupo de integração e de fechamento (`canonical_full_gate`) passa com exit 0;
3. O status do lote em `batches/Bnnn.md` é atualizado para `done`;
4. `active_batch` em `STATUS.md` é atualizado para `none` e `batch_status: none`;
5. É gerado o relatório final ao usuário contendo sumário de unidades, chamadas consumidas e evidências;
6. O sistema retorna para `IDLE`.
- **Invariante:** O fechamento de um lote **nunca** gera ou inicia automaticamente um novo lote.

---

## 8. Mapeamento Documental e Governança de Independência

### 8.1 Mapeamento Documental
- Verificou-se que `docs/EXECUTION_PROTOCOL.md` não existe no repositório. As regras normativas de protocolo de execução, coordenação, esperas, liveness e filas pertencem canonicamente a `docs/WORK_MODEL.md` e `prompts/orchestrator-playbook.md`. Criar um arquivo novo causaria fragmentação de autoridade; portanto, as regras normativas do Modo Automático são incorporadas diretamente nesses dois documentos existentes.

### 8.2 Autoria e Independência de T018
- A especificação final de T018 incorpora formalmente autoria material acumulada `[openai, google, anthropic]`.
- No catálogo atual composto pelas três famílias, inexiste quarta família para atuar como revisor independente `full_cross_family`.
- Por conseguinte, a verificação de T018 opera sob `checker_independence: preferred`, admitindo fallback degradado na mesma família em sessão nova (`same_family_fresh_session`) com justificativa registrada como limitação conhecida, vedando-se a configuração `required` que geraria bloqueio insolúvel no catálogo atual.
