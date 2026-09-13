id: T014
type: feat
deliverable: package
standalone: true
method: native
status: done
state_revision: 1
depends_on: [T013]
blocked_by: []
origin: user (2026-09-13: "Comece pela 1 e logo apos terminar vá para a 2", "Quero Basicamente Resiliencia para poder deixar o orquestrador e sair do pc e ir dormir por exemplo e continuar rodando sozinho a noite toda, reduzir custo com inteligencia, estabilidade para não atrasar as tarefas travando ou parando por causa de algum problema, e tbm velocidade que é uma das coisas que tá mais me frustando atualmente é a demora")
decisions: []
spec_author: orchestrator
spec_revision: 1
rework_round: 0
affects_context: []
content_paths: [docs/EXECUTION_PROTOCOL.md, prompts/orchestrator-playbook.md, CHANGELOG.md, _tl-orc/project/STATUS.md]
content_id: auto
worktree: branch feat/pipelining-e-heartbeat

## Finding
source: auditoria de telemetria real em projeto consumidor e síntese arquitetural cruzada com Claude (Fable 5.1) e Codex Astra
observed: A execução sequencial de stories sofria com um gargalo de ~47 minutos de espera passiva e bloqueios: (1) 10 minutos de espera síncrona pelo CI remoto do GitHub Actions após `gh pr create`; (2) 15 minutos de travamento por locks órfãos (`session.lock`) quando uma sessão caía sem liberação atômica; (3) 6 minutos de execução repetida de todos os 11 gates mesmo em alterações mínimas; (4) loops de correção entre Maker e Checker sem estacionamento automático.
expected: O condutor e o protocolo de execução devem formalizar: (a) Pipelining assíncrono com Git worktrees (abertura de PR não bloqueia a próxima story independente no DAG); (b) Heartbeat e fencing de leases com recuperação atômica de locks órfãos; (c) Teto de 2 rodadas com estacionamento (`parked`) e detector de oscilação de diff para autonomia noturna contínua; (d) Cache de gates por hash de árvore (`tree_sha`).
impact: Redução drástica do tempo de ciclo de ~55 minutos para ~15 a 18 minutos por story, eliminando deadlocks e permitindo execução autônoma prolongada sem intervenção humana.

## Spec
### Intent
Incorporar no protocolo de execução (`docs/EXECUTION_PROTOCOL.md`) e no playbook do orquestrador (`prompts/orchestrator-playbook.md`) os mecanismos formais de pipelining assíncrono com Git worktrees, heartbeat de leases, estacionamento automático anti-loop e cache de gates por árvore.
### Scope and write paths
- `docs/EXECUTION_PROTOCOL.md`: protocolo formal de pipelining assíncrono, heartbeat de leases e ciclo noturno.
- `prompts/orchestrator-playbook.md`: diretrizes operacionais de avanço na fila sequencial com pipelining e estacionamento de stories.
- `CHANGELOG.md`: documentação das melhorias na versão `0.10.0`.
- `_tl-orc/project/STATUS.md`: registro de T014.
