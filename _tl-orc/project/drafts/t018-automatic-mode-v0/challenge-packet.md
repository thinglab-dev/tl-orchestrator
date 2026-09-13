# Challenge Packet — Advisor Consultivo

```yaml
challenge_subject: "T018 Automatic Mode — pre-spec architecture v0"

status:
  task_created: false
  spec_frozen: false
  implementation_authorized: false

objective:
  "Permitir execução autônoma de um lote finito e explicitamente
   autorizado de unidades já conhecidas, sem expansão silenciosa
   de autoridade, escopo ou custo."

triggers:
  - shared_architecture_and_governance
  - difficult_to_reverse_operational_authority
  - high_cost_automatic_batch

challenged_author_families:
  - openai
  - google

known_constraints:
  - user authority remains exclusive
  - discover/propose are read-only
  - explicit authorization required before freeze
  - new work outside frozen batch requires new authorization
  - one writer per tree
  - per-phase classifier remains mandatory
  - checker independence remains mandatory according to local policy
  - T015 context economy applies
  - T016 verification cadence applies
  - T017 advisor triggers apply
  - no implicit external effects
  - no daemon or self-authorizing loop

architecture_under_challenge:
  state_machine: "DISCOVER → PROPOSE → WAIT_AUTHORIZATION → FREEZE_BATCH → EXECUTE → CLOSE"
  membership: "snapshot of explicitly proposed existing units"
  default_on_block: "stop at first blocked unit (continue_independent_after_block: false)"
  rework: "automatic only for Maker findings inside frozen spec/scope/budget"
  budget: "finite model-call and rework limits based on observable actual calls"
  recovery: "durable checkpoint + revalidation"
  new_batch_after_close: "never automatic"

open_architecture_decision:
  durable_batch_state:
    - "A: new Batch entity (_tl-orc/project/batches/Bnnn.md)"
    - "B: extend QUEUE/STATUS with batch snapshot and authorization"
    - "C: runtime-only in memory"

specific_question:
  "Does this architecture provide the minimum sufficient guarantees
   for autonomous execution without scope creep, hidden authority
   expansion, infinite rework, recursive advisory, invalid continuation,
   or uncontrolled cost? What must change before T018 can be frozen?"

requested_analysis:
  - authorization boundary (DISCOVER -> PROPOSE vs EXECUTE authorization)
  - batch membership semantics (frozen snapshot vs dynamic additions)
  - state persistence/recovery (comparative analysis of options A, B, and C)
  - stop conditions (exhaustiveness and failure modes)
  - rework authority (strict boundaries on automatic changes_requested resolution)
  - budget exhaustion (observable call accounting vs unobservable token quotas)
  - advisor recursion (non-recursive execution and cost containment)
  - classifier/checker independence (guarantees across sequential autonomous units)
  - integration boundaries (T016 targeted tests vs boundary canonical full gates)
  - external effects (absolute prohibition of push, PR, merge, tags, releases)
```

## Contexto e Rascunho Completo sob Desafio
O documento arquitetural completo encontra-se em:
[_tl-orc/project/drafts/t018-automatic-mode-v0/architecture-draft-v0.md](architecture-draft-v0.md)
