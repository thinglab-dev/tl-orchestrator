# Rascunho Arquitetural v0 — Modo Automático (T018)

**Status do Artefato:** Rascunho pré-especificação sob desafio consultivo (Pre-spec Architecture under Challenge).  
**Task Formal Criada:** Não (`_tl-orc/project/tasks/T018...md` inexistente).  
**Spec Congelada:** Não.  
**Implementação Autorizada:** Não.  
**Autoria Material:** OpenAI (arquitetura concebida e proposta pelo mantenedor) + Google (formalização estrutural, integração contratual e salvaguardas pelo Orquestrador Antigravity).  
**Famílias Autoras (`challenged_author_families`):** `[openai, google]`

---

## 1. Objetivo e Fronteira de Autoridade

### 1.1 Objetivo Central
Executar autonomamente um **lote finito e explicitamente autorizado** de unidades já conhecidas do projeto, preservando:
1. Autoridade humana exclusiva sobre escopo, orçamento e efeitos colaterais;
2. Escopo estritamente congelado no início da execução;
3. Orçamento observável limitado (chamadas efetivamente realizadas e limites de retrabalho);
4. Independência rigorosa dos revisores (Checker e Advisor conforme políticas vigentes);
5. Verificação econômica contínua (testes direcionados intragrupo e portões canônicos completos nas fronteiras maiores — T016);
6. Recuperação durável, auditável e segura após interrupção.

### 1.2 Não-Objetivos (Anti-Patterns Expressamente Vedados)
- **Não** criar um agente indefinidamente autônomo;
- **Não** percorrer backlog de forma ilimitada ou descontrolada;
- **Não** criar ou formalizar novas Tasks espontaneamente;
- **Não** auto-autorizar escopo, orçamento, efeitos ou exceções;
- **Não** manter serviços em segundo plano, daemons permanentes ou loops de polling contínuo;
- **Não** presumir nem executar `git push`, PR, merge remoto, tags git ou publicações externas sem comando humano prévio e explícito.

---

## 2. Máquina de Estados do Modo Automático

```text
IDLE
  ↓ comando explícito do usuário: "iniciar modo automático"
DISCOVER                # read-only: inspeção de unidades candidatas existentes
  ↓
PROPOSE                 # read-only: geração da proposta formal de lote
  ↓
WAIT_AUTHORIZATION      # bloqueio síncrono aguardando aprovação explícita
  ↓ resposta humana aprovando integralmente a proposta
FREEZE_BATCH            # snapshot imutável da autoridade, unidades, políticas e orçamento
  ↓
EXECUTE                 # loop de execução sequencial controlada por unidade
  ↓
CLOSE                   # fechamento do lote com relatório terminal

Saídas Excepcionais (Terminais ou com Ponto de Retomada):
BLOCKED | STOPPED | FAILED | PARTIAL | CANCELLED
```

### 2.1 Invariante de Autorização Inicial
```text
"iniciar modo automático" ≠ autorização para executar
```
O comando inicial do usuário autoriza **única e exclusivamente** a fase de leitura `DISCOVER → PROPOSE`.  
Nenhuma modificação de código, commit, mutação de estado ou despacho de agente de implementação pode ocorrer antes de uma segunda resposta humana formal que aprove a proposta apresentada.

### 2.2 Estrutura da Proposta (`PROPOSE`)
A fase `PROPOSE` devolve ao usuário um objeto estruturado completo para deliberação:
```yaml
proposal:
  proposal_id: "prop-20260912-001"
  candidate_units: ["T018", "T019", "T020"]
  order: ["T018", "T019", "T020"]
  dependencies:
    T018: []
    T019: ["T018"]
    T020: ["T019"]
  integration_groups:
    T018: "group-alpha"
    T019: "group-alpha"
    T020: "group-beta"
  expected_roles: ["classifier", "maker", "checker", "advisor_if_triggered"]
  allowed_effects:
    local_write: true
    local_commit: true
    local_merge: false
    push: false
    pull_request: false
    tag: false
    release: false
  excluded_effects: ["push", "pull_request", "tag", "release", "external_api_write"]
  model_call_budget: 18
  max_rework_rounds_per_unit: 2
  advisor_budget: 3
  continue_independent_after_block: false
  verification_plan:
    intragroup: "targeted_tests"
    boundaries: ["group-alpha -> group-beta", "batch_closure"]
  major_boundaries:
    - from: "group-alpha"
      to: "group-beta"
      gate: "python3 scripts/validate_repository.py"
  stop_conditions:
    - authority_missing_or_ambiguous
    - scope_expansion
    - model_call_budget_exhausted
    - rework_limit_exhausted
    - bad_spec_or_intent_gap
    - canonical_full_gate_failure
    - unexpected_revision_drift
    - external_effect_not_authorized
```

---

## 3. Congelamento do Lote (`FREEZE_BATCH`)

Ao receber a autorização explícita do usuário, o sistema materializa o snapshot imutável do lote:

```yaml
batch:
  batch_id: "B001"
  proposal_digest: "sha256:..."
  authority:
    source: "explicit_user_authorization"
    scope_digest: "sha256:..."
    authorized_at: "2026-09-12T15:00:00Z"

  units:
    - work_ref: "T018"
      revision: 1
      spec_revision: "..."
      integration_group: "group-alpha"
      dependencies: []
    - work_ref: "T019"
      revision: 1
      spec_revision: "..."
      integration_group: "group-alpha"
      dependencies: ["T018"]

  permitted_effects:
    local_write: true
    local_commit: true
    local_merge: false
    pull_request: false
    push: false
    tag: false
    release: false

  budget:
    max_model_calls: 18
    max_rework_rounds_per_unit: 2
    max_advisor_calls: 3
    consumed_model_calls: 0
    consumed_advisor_calls: 0

  policies:
    context: "T015"
    verification: "T016"
    advisor: "T017"
    participant_selection: "T014"
    execution_waiting: "T013"

  stop_conditions: [...]

  current_unit: "T018"
  batch_status: "in_progress"
  batch_revision: 1
```

### 3.1 Unidade de Orçamento Observável
O orçamento é computado estritamente sobre **chamadas efetivamente realizadas a modelos e observadas pelo Orquestrador**. Estimativas de quota, tokens restantes de planos não observáveis ou faturas de provedores não são aceitas como métrica de controle de execução.

### 3.2 Semântica de Associação ao Lote (*Batch Membership*)
- No momento do `FREEZE_BATCH`, congelam-se exclusivamente as unidades elegíveis já existentes encontradas no `DISCOVER` e aprovadas no `PROPOSE`.
- Qualquer nova Task ou Deliverable descoberto ou criado durante a execução **não pertence ao lote congelado**. O avanço sobre novos itens exige novo ciclo `DISCOVER → PROPOSE → AUTHORIZE`.
- Rodadas de retrabalho (*rework*) da **mesma unidade** não constituem nova unidade e podem prosseguir automaticamente desde que:
  1. O achado do Checker seja direcionado ao Maker (`target_role == maker`);
  2. A correção caiba estritamente na especificação (`spec_revision`) congelada;
  3. A correção caiba nos caminhos de conteúdo (`content_paths`) congelados;
  4. Não haja alteração de autoridade, produto ou arquitetura;
  5. Haja saldo no orçamento de retrabalho e de chamadas do lote.

---

## 4. Loop de Execução por Unidade (`EXECUTE`)

Para cada unidade do lote congelado:

```text
LOAD authoritative state
        ↓
validate revision / scope / coordinator / working tree
        ↓
Classifier da fase (obrigatório por fase, perfil fixo, sem auto-seleção de modelo/effort)
        ↓
Advisor? ─── acionado SOMENTE se houver trigger objetivo de T017
        ↓
Planner? ─── acionado SOMENTE se houver necessidade real e autorização de planejamento
        ↓
Maker (implementação dentro dos content_paths)
        ↓
Targeted Verification (T016 — suíte direcionada)
        ↓
Checker Independente (T014 / T017 — fresh session, report-only, contra-família)
        ↓
approved?
 ├── SIM → marca unidade concluída
 └── NÃO
       ↓
     action items do Checker
       ├── Maker + mesmo escopo + budget → rework automático
       └── bad_spec / intent_gap / human / expansão de escopo → STOP
        ↓
mudou integration_group?
 ├── NÃO → avança para a próxima unidade do lote
 └── SIM → executa canonical_full_gate oficial na fronteira
              ├── PASS → avança para a próxima unidade
              └── FAIL → STOP imediato (bloqueio na fronteira)
```

### 4.1 Limites Estritos de Retrabalho Automático
O avanço automático em `changes_requested` é restrito e deve interromper imediatamente (`STOP`) perante qualquer uma das seguintes situações:
- Achado classificado como `bad_spec` ou `intent_gap`;
- Destinatário da ação `target_role == human`;
- Necessidade de nova decisão de produto ou design;
- Alteração arquitetural não prevista na spec congelada;
- Necessidade de alterar caminhos fora dos `content_paths` congelados;
- Tentativa de criar nova Task;
- Tentativa de efeito colateral externo não autorizado;
- Esgotamento de rodadas de retrabalho da unidade ou do orçamento do lote.

---

## 5. Condições Formais de Parada (*Stop Conditions*)

O Modo Automático deve interromper a execução (`STOP`) e devolver o controle imediato ao usuário quando qualquer uma das seguintes condições for detectada:

1. `authority_missing_or_ambiguous`: ausência de autorização formal para a ação solicitada.
2. `scope_expansion`: tentativa de alterar arquivos ou comportamentos fora dos limites congelados.
3. `new_work_outside_frozen_batch`: surgimento ou necessidade de unidade de trabalho fora do lote.
4. `model_call_budget_exhausted`: consumo total do orçamento de chamadas autorizado para o lote.
5. `rework_limit_exhausted`: atingimento do limite máximo de rodadas de retrabalho da unidade.
6. `required_checker_independence_unavailable`: indisponibilidade de revisor independente sob política `required`.
7. `required_advisor_independence_unavailable`: indisponibilidade de consultor independente sob política `required`.
8. `advisor_verdict_stop`: parecer de parada emitido pelo Advisor.
9. `advisor_verdict_debate` (ou `debate_required: true`): necessidade de deliberação sem autorização prévia para painel de debate.
10. `bad_spec_or_intent_gap`: especificação inconsistente, contraditória ou com lacuna de intenção do usuário.
11. `canonical_full_gate_failure`: falha na execução do portão canônico de integração em fronteira maior.
12. `coordinator_conflict`: alteração ou conflito no coordenador da árvore.
13. `foreign_dirty_tree`: modificações não autorizadas, arquivos órfãos ou alterações externas na árvore de trabalho.
14. `unexpected_revision_drift`: divergência de revisão em relação ao snapshot congelado do lote.
15. `external_effect_not_authorized`: tentativa de invocar rede, push, merge externo, tag ou release.
16. `unrecoverable_harness_failure`: falha persistente e irrecuperável de infraestrutura de harness.
17. `dependency_block`: bloqueio de dependência de uma unidade do lote.
    - **Regra de bloqueio de dependência:** o comportamento padrão é `continue_independent_after_block: false`. O lote é interrompido no primeiro bloqueio. A continuidade sobre unidades independentes só é admitida se explicitamente configurada pelo usuário na autorização do lote.

---

## 6. Integração com Mecanismos Existentes (T013–T017)

O Modo Automático **compõe e orquestra** os contratos já estabelecidos, sem reinventá-los:
- **T013 (Execution Waiting & Batch):** regras de liveness, tolerância proporcional a esperas mecânicas e retomadas sem polling infinito;
- **T014 (Participant Selection & Independence):** seleção de perfis, cadeia nominal e independência rigorosa de Checker;
- **T015 (Context Economy):** resumos estruturados, selective retrieval, preservação de ledgers e handoffs econômicos;
- **T016 (Verification Cadence):** testes direcionados intragrupo durante implementação/rework; execução do `canonical_full_gate` oficial exclusivamente nas fronteiras de grupo de integração e no fechamento do lote;
- **T017 (Advisor):** acionamento estrito por gatilhos objetivos; resolução de contra-família contra o conjunto completo de autores materiais; vedações estritas contra auto-autorização e recursão.

### 6.1 Vedação de Recursão do Advisor
Durante o Modo Automático, o papel Advisor é estritamente não recursivo:
- O Advisor não pode invocar outro Advisor;
- O Advisor não pode autorizar outro Advisor;
- O Advisor não pode expandir a política `advisor_policy`;
- O Advisor não pode aumentar seu próprio orçamento de chamadas.
- Todas as chamadas de Advisor são debitadas do orçamento dedicado `max_advisor_calls`.

### 6.2 Consumo dos Vereditos do Advisor
- `proceed`: execução continua;
- `adjust`: aplicada automaticamente apenas se couber estritamente no lote congelado e no orçamento; caso contrário `STOP`;
- `plan`: despacho de Planner somente se explicitamente autorizado no lote; caso contrário `STOP`;
- `debate` (ou `debate_required: true`): despacho de Debate somente se previamente autorizado; caso contrário `STOP`;
- `stop`: interrupção imediata da execução do lote.

---

## 7. Recuperação e Retomada de Interrupções

O Modo Automático não utiliza serviços imortais em segundo plano. Toda execução é apoiada em persistência durável de estado:
Ao retomar uma execução interrompida:
1. Carrega o estado durável do lote;
2. Revalida a autoridade, `batch_revision`, revisões das unidades, coordenador, árvore de trabalho (`git status`), orçamento consumido e identificadores de conteúdo (`spec_revision`, `content_id`);
3. Se todos os invariantes conferirem: retoma exatamente a partir do checkpoint persistido;
4. Se houver qualquer divergência ou deriva não explicada: aborta a retomada com `STOP` e exige conciliação humana.

---

## 8. Fechamento do Lote (`CLOSE`)

O lote encerra-se quando:
- A última unidade terminal é concluída com sucesso;
- Os portões canônicos completos de fronteira (`canonical_full_gate`) foram validados com exit 0;
- O estado do lote é atualizado para `batch_status: done`;
- É emitido um relatório final completo ao usuário contendo unidades concluídas, rodadas de retrabalho, chamadas a modelos consumidas e evidências produzidas;
- O sistema retorna para `IDLE`.
- **Invariante:** O fechamento de um lote **nunca** gera ou inicia automaticamente um novo lote.

---

## 9. Decisão Arquitetural Aberta: Persistência do Estado Durável do Lote

Submetem-se ao Advisor três alternativas de persistência do estado do lote para avaliação crítica de trade-offs:

### Alternativa A: Nova Entidade Batch em `_tl-orc/project/batches/Bnnn.md`
- **Conceito:** Criar um diretório próprio e formato padronizado de documento Markdown com frontmatter estruturado (semelhante às Tasks) dedicado ao ciclo de vida do lote (`batch_id`, autoridade, snapshot de unidades, orçamentos, revisões, checkpoints de progresso e log de chamadas).
- **Vantagens:** Isolamento total de responsabilidades; desacoplamento da fila operacional (`QUEUE.md`); histórico imutável por lote; persistência natural no controle de versão local.
- **Riscos / Desvantagens:** Introduz uma nova entidade no modelo de governança; amplia o número de schemas e arquivos monitorados.

### Alternativa B: Estender `QUEUE.md` e `STATUS.md` com Bloco de Autorização e Snapshot de Lote
- **Conceito:** Incorporar campos de autorização de lote, snapshot de membros e contadores de orçamento diretamente nas estruturas existentes (`QUEUE.md` para a fila ordenada e `STATUS.md` para o estado de execução).
- **Vantagens:** Reutiliza arquivos existentes sem criar novas entidades no repositório.
- **Riscos / Desvantagens:** Mistura estado efêmero de sessão/batch com a fila perene de governança; risco de corrupção ou conflito de concorrência em arquivos centrais; dificulta auditoria histórica de lotes passados.

### Alternativa C: Lote Apenas em Memória / Runtime de Execução
- **Conceito:** O lote existe apenas no contexto de execução do harness durante a sessão do Orquestrador, sem arquivo durável dedicado no repositório.
- **Vantagens:** Zero overhead de escrita em disco; modelo simples durante execuções ininterruptas.
- **Riscos / Desvantagens:** Perda total de rastreabilidade em caso de crash do processo ou timeout; impossibilidade de recuperação auditável após interrupção; ausência de prova durável de autorização humana.
