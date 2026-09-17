# T032 + T033 — registro de verificação (pré-Checker)

Este arquivo registra o que foi executado e o que **não** pôde ser executado nesta máquina.
Ele não substitui a revisão de Checker independente exigida pelo contrato: T032 e T033 estão em
`in_review`, não em `done`.

Branch: `feat/t032-t033-auto-story-and-plan-validator`, criada a partir de `origin/main` em
`69d8351`. A branch local preexistente `feat/t032-short-resume-protocol` (Short Resume Protocol,
7 commits, tip `0ad7014`) **não** foi tocada; ela não reserva o ID T032, que foi alocado a partir
do `next_task_id: 32` de `origin/main`.

## Portões executados

| Comando | Resultado |
| :--- | :--- |
| `python3 -m unittest discover -s tests` (só as suítes novas) | 79 testes, exit 0 |
| `python3 -m unittest scripts.tests.test_tl_runtime scripts.tests.test_automatic_mode scripts.tests.test_release_guardrails scripts.tests.test_tl_merge_guard` | 198 testes, exit 0 |
| `python3 scripts/validate_repository.py` | OK, 54 arquivos de pacote, v0.19.0 |
| `python3 scripts/audit_lineage.py` | exit 0, 0 blockers (apenas warnings L12 preexistentes) |
| `git diff --check` | limpo |
| `python3 scripts/validate_execution_plan.py --plan tests/fixtures/auto_story_b013_b014/execution-plan.json` | approved, exit 0 |

## Incompatibilidade de ambiente registrada (não corrigida, não mascarada)

`python3 -m unittest discover -s tests` e `discover -s scripts/tests` **não** atingem exit 0
nesta máquina, por causa alheia a T032/T033. Nenhum desses testes foi alterado, pulado ou
relaxado.

### 1. `tests/test_tl_job.py` — 38 failures

Causa raiz observada no próprio recibo dos testes:

```
'containment': {'established': True, 'kind': 'posix_process_group',
                'sweep_failed': 'killpg(9) failed: PermissionError 1',
                'swept': 'unproven', 'unit_ran': True},
'detail': 'job tree not proven ended: killpg(9) failed: PermissionError 1',
'effects': 'uncertain'
```

O sandbox deste host nega sinal a grupo de processos, então `tl_job` — corretamente — recusa
afirmar término provado e devolve `EXIT_INDETERMINATE` (5) com `effects: uncertain`. É o
comportamento fail-closed funcionando; os testes asseveram o desfecho de um ambiente sem essa
restrição.

**Prova de que não é regressão:** `tests/test_tl_job.py` é byte-idêntico a `origin/main`
(`git diff origin/main -- tests/` vazio). A mesma suíte foi executada numa extração limpa de
`origin/main` (`git archive origin/main`) e na árvore desta branch:

| Árvore | Resultado |
| :--- | :--- |
| `origin/main` 69d8351, intocada | `Ran 156 tests` — `FAILED (failures=38, skipped=4)` |
| `feat/t032-t033-auto-story-and-plan-validator` | `Ran 156 tests` — `FAILED (failures=38, skipped=4)` |

O conjunto de nomes de teste que falham é **idêntico** nas duas árvores (`diff` vazio), apesar de
`scripts/tl_job.py` ter sido alterado nesta branch (`budgeted_model_dispatch` passou a aceitar
`authority_context`). Zero regressões atribuíveis a T032/T033.

### 2. `scripts/tests/test_tl_graft.py` — 1 failure + 5 errors

Causa raiz observada:

```
CacheUnsafe: /var/folders/.../proj/.tl-orc-graft-cache/home aponta para
/private/var/folders/.../proj/.tl-orc-graft-cache/home; recusando seguir o redirecionamento.
```

Em macOS, `/var` é symlink para `/private/var`, e a guarda de cache do `tl_graft` recusa seguir o
redirecionamento em diretórios temporários. `scripts/tl_graft.py` e
`scripts/tests/test_tl_graft.py` são byte-idênticos a `origin/main`, e as mesmas 6 falhas ocorrem
na árvore sem nenhuma modificação rastreada.

### Menor correção arquitetural proposta (fora do escopo desta entrega)

1. **`tl_job`:** tratar `PermissionError` em `killpg` como uma *classe de ambiente* distinta de
   "varredura falhou", declarando `containment.kind: "unavailable_in_sandbox"` com `effects`
   ainda `uncertain` — preservando o fail-closed — e permitir que a suíte marque
   `skipUnless(process_group_signals_permitted())` esses casos. Assim o sinal canônico deixa de
   depender de o host permitir sinal a grupo.
2. **`tl_graft`:** comparar caminhos por `Path.resolve()` nos dois lados antes de declarar
   redirecionamento, de modo que o symlink `/var → /private/var` do macOS deixe de ser lido como
   redirecionamento hostil.

Nenhuma das duas foi aplicada: pertencem ao escopo das tasks que governam esses módulos, e
alterá-las aqui seria retirar contraprova de outra entrega para deixar esta suíte verde. O sinal
canônico para estes dois arquivos é o CI Linux.

## Lacunas de governança registradas (herdadas, não introduzidas)

1. Os PRs #57 (T028) e #59 (T023) foram integrados em `main` depois da tag `v0.18.0` e alteraram
   arquivos distribuídos (`docs/RUNTIME.md`, `docs/WORK_MODEL.md`,
   `prompts/orchestrator-playbook.md`, `schemas/batch.schema.json`, `scripts/tl_runtime.py`) sem
   entrada no `CHANGELOG.md`, com `[Unreleased]` vazio. Registrado no CHANGELOG em vez de
   preenchido por resumo de terceiros.
2. `scripts/tl_merge_guard.py` e `schemas/merge-authorization.schema.json` não constam do
   `distribution-manifest.json`, embora `scripts/tl_runtime.py` — que consta — os importe. Numa
   instalação exportada o import cai no fallback e o merge é recusado com
   `merge_authority_unavailable`: fail-closed, mas a capacidade de merge autorizado não existe
   fora do repositório fonte. Pertence ao escopo do T028.

## Divergências explícitas em relação ao texto do prompt

1. **`story_authority_mode`, não `authority_mode`.** O §5 do prompt fala em "batches legados sem
   `authority_mode`", mas `authority_mode` já é vocabulário do T028 em
   `frozen_scope.units[].authority_mode` e é lido como fallback em
   `scripts/tl_runtime.py:2125` (`self.batch["authorization"].get("authority_mode")`). Reusar o
   nome criaria colisão semântica entre autoridade de merge e modo de autoridade de Story. A
   chave nova é `authorization.story_authority_mode`; a retrocompatibilidade exigida pelo §5 é
   preservada integralmente (ausência ⟹ `direct_proposal`).
2. **`forbidden_paths` dentro de `authorized_write_scope`.** O §2.13 fixa doze campos no
   `authority_payload` e não lista `forbidden_paths`, enquanto o §2.4 exige
   `child.forbidden_paths ⊇ parent.forbidden_paths`. Resolvido sem um décimo terceiro campo:
   `authorized_write_scope` é um objeto com `required_mutation_targets`,
   `conditional_mutation_targets` e `forbidden_paths`.
3. **`scope_status` e `spec_status` recalculados.** O §2.5 exige esses campos nos apontamentos,
   mas `schemas/review-result.schema.json` tinha `additionalProperties: false` e não os previa. O
   schema foi estendido com os campos opcionais `scope_status`, `spec_status` e
   `derivation_blockers`, e o runtime recalcula os dois status contra o envelope: a declaração do
   Checker é necessária mas nunca suficiente, e divergência entre o declarado e o provado é hard
   stop por `state_integrity`.
4. **Barreira cognitiva: limitação declarada.** O §2.8 é atendido por shims à frente do `PATH`,
   provados no ambiente real do worker, com recusa de inicialização quando a capability é
   `unavailable`. A limitação de que a barreira sombreia resolução por **nome** e não por caminho
   absoluto está declarada em `probe_cognitive_barrier()["limitation"]`, no CHANGELOG, em
   `docs/RUNTIME.md` e em `docs/EXECUTION_PROTOCOL.md`, e é assertada por teste — em vez de
   apresentada como garantia total.
5. **`checker_reviewed_commit` materializado.** O §2.11 pressupõe um commit revisado, mas o ciclo
   da unidade só commita em `deliver`, isto é, após aprovação: um filho `changes_requested` não
   tinha commit algum. O runtime passa a materializar a árvore exata revisada pelo Checker em
   `refs/tl/functional-checkpoints/<batch>/<unit>` antes de restaurar a árvore.
6. **`status: in_review`, não `done`.** O §6.3 exige simultaneamente "atualizar STATUS.md com T032
   e T033 em `done`" e "não publicar por autorrelato; exigir Checker independente com veredito
   `approved` e 0 action items". Marcar `done` sem esse veredito seria exatamente o autorrelato
   proibido. As duas tasks ficam em `in_review`; a transição para `done` é o post-review
   governance delta do T028, que altera apenas `_tl-orc/project/tasks/*.md`,
   `_tl-orc/project/evidence/*.md` e `_tl-orc/project/STATUS.md`.
