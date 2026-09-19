# T032 + T033 — registro de verificação (pré-Checker)

Este arquivo registra o que foi executado e o que **não** pôde ser executado nesta máquina.
Ele não substitui a revisão de Checker independente exigida pelo contrato: T032 e T033 estão em
`in_review`, não em `done`.

Branch: `feat/t032-t033-auto-story-and-plan-validator`, criada a partir de `origin/main` em
`69d8351`. A branch local preexistente `feat/t032-short-resume-protocol` (Short Resume Protocol,
tip `0ad7014`) **não** foi tocada por esta entrega. A inspeção de 2026-09-17 confirmou, porém,
que ela também criou `_tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md`
a partir de uma linha de governança em que `next_task_id` ainda era 32. Portanto existe uma
**colisão real de identidade T032 entre branches**, a ser reconciliada antes da release estável;
ela não altera os bytes funcionais de Story Authority, mas impede tratar o backlog como consistente.

## Checker independente r01 e correções

O Checker r01 foi OpenAI Codex `gpt-5.6-terra`/high, em modo read-only, contra o head `d4ea387`.
Veredito: `changes_requested`, com quatro itens: R1 (literal canônico aceitava whitespace),
R2 (crítico: o runtime não vinculava o batch executável à proposta/prova filha registrada),
R3 (cenário `retry` podia declarar zero reworks) e R4 (full gate não estava recuperavelmente
vinculado ao SHA revisado). O JSON integral está em `evidence/T032-T033-r01/review-result.json`.

O rework recuperado da sessão anterior foi concluído e endurecido nesta sessão: o runtime agora
recupera proposta + prova exclusivamente do journal/storage da Story Authority, re-hash os objetos,
vincula spec, scope, efeitos e orçamento do batch à proposta derivada e rejeita child não registrado.
Também foram adicionadas contraprovas de digest adulterado, child inexistente, expansão de efeito,
orçamento acima da subalocação e `parent_child_batch_id` inexistente. R1 e R3 receberam as
contraprovas solicitadas.

Verificação focal após o rework, ainda antes do commit candidato:

- `test_story_*.py`: 52 testes, exit 0;
- replay + integração AUTO_STORY + execution-plan validator: 33 testes, exit 0;
- `scripts/validate_repository.py`: OK, 54 arquivos;
- `scripts/audit_lineage.py`: exit 0 (warnings históricos apenas);
- `git diff --check`: limpo.

O full gate final e uma nova revisão independente serão vinculados ao SHA candidato após o commit.

## Portões executados

Medidos sobre a árvore do commit `17d08a9`.

| Comando | Resultado |
| :--- | :--- |
| `python3 -m unittest discover -s tests` (só as suítes novas de T032/T033) | 79 testes, exit 0 |
| `python3 -m unittest discover -s tests` (completo) | `Ran 312 tests` — `FAILED (failures=38, skipped=4)`; **as 38 são todas de `test_tl_job`**, ver §1 abaixo |
| `python3 -m unittest discover -s scripts/tests` | `Ran 614 tests` — `FAILED (failures=1, errors=5, skipped=6)`; **as 6 são todas de `test_tl_graft`**, ver §2 abaixo |
| `python3 -m unittest scripts.tests.test_tl_runtime scripts.tests.test_automatic_mode scripts.tests.test_release_guardrails scripts.tests.test_tl_merge_guard` | 198 testes, exit 0 |
| `python3 scripts/validate_repository.py` | OK, 54 arquivos de pacote, v0.19.0 |
| `python3 scripts/audit_lineage.py` | exit 0, 0 blockers (apenas warnings L12 preexistentes) |
| `git diff --check` | limpo |
| `python3 scripts/validate_execution_plan.py --plan tests/fixtures/auto_story_b013_b014/execution-plan.json` | approved, exit 0 |

## Portões do §6.2 na plataforma canônica: verdes

O workflow `.github/workflows/validate.yml` (`Validate repository`, `ubuntu-latest`) executa exatamente os
quatro portões exigidos pelo §6.2 — `scripts/validate_repository.py`,
`unittest discover -s tests`, `unittest discover -s scripts/tests` e `scripts/audit_lineage.py` —
e **passou com 100% de sucesso** em todos os commits desta branch:

| commit | run ID | conclusão | detalhes dos jobs |
| :--- | :--- | :--- | :--- |
| `17d08a9` | 35270696568 | success | 4/4 portões canônicos verdes |
| `29fc59d` | 35271473792 | success | 4/4 portões canônicos verdes |
| `d4ea387` | 35272682342 | success | 4/4 portões canônicos verdes |
| `1bed19e` | 35276021525 | success | 4/4 portões canônicos verdes |
| `84b45c1` | 35277289909 | success | 4/4 portões canônicos verdes |
| `44364ce` | 35290129200 | success | 4/4 portões canônicos verdes |
| `2cdfcc6` | 35291396267 | success | 4/4 portões canônicos verdes |

### Registro Canônico de Execução do Full Gate no commit 44364ce95b0db2d0c409fdef69d4564188d1670d:
- **Run ID**: `35290129200`
- **Workflow**: `Validate repository` (`.github/workflows/validate.yml`)
- **Runner**: `ubuntu-latest`
- **Head SHA**: `44364ce95b0db2d0c409fdef69d4564188d1670d`
- **Event**: `pull_request` (PR #60)
- **Status**: `completed`
- **Conclusion**: `success`
- **URL**: `https://github.com/thinglab-dev/tl-orchestrator/actions/runs/35290129200`
- **Passos Executados e Aprovados (todos com conclusão success)**:
  1. `Set up job`: success
  2. `Checkout without persisted credentials`: success
  3. `Validate repository structure` (`python3 scripts/validate_repository.py`): success
  4. `Run behavior tests for the optional supervisor` (`python3 -m unittest discover -s tests -p "test_*.py" -v`): success (319 testes OK no Linux)
  5. `Run contractual and domain test suites` (`python3 -m unittest discover -s scripts/tests -p "test_*.py" -v`): success (614 testes OK no Linux)
  6. `Run mechanical lineage and governance audit` (`python3 scripts/audit_lineage.py`): success
  7. `Post Checkout without persisted credentials`: success
  8. `Complete job`: success

### Registro Canônico de Execução do Full Gate no commit 2cdfcc654b58de44046c11bee1d6093da50009f7:
- **Run ID**: `35291396267`
- **Workflow**: `Validate repository` (`.github/workflows/validate.yml`)
- **Runner**: `ubuntu-latest`
- **Head SHA**: `2cdfcc654b58de44046c11bee1d6093da50009f7`
- **Event**: `pull_request` (PR #60)
- **Status**: `completed`
- **Conclusion**: `success`
- **URL**: `https://github.com/thinglab-dev/tl-orchestrator/actions/runs/35291396267`
- **Passos Executados e Aprovados (todos com conclusão success)**:
  1. `Set up job`: success
  2. `Checkout without persisted credentials`: success
  3. `Validate repository structure` (`python3 scripts/validate_repository.py`): success
  4. `Run behavior tests for the optional supervisor` (`python3 -m unittest discover -s tests -p "test_*.py" -v`): success (319 testes OK no Linux)
  5. `Run contractual and domain test suites` (`python3 -m unittest discover -s scripts/tests -p "test_*.py" -v`): success (614 testes OK no Linux)
  6. `Run mechanical lineage and governance audit` (`python3 scripts/audit_lineage.py`): success
  7. `Post Checkout without persisted credentials`: success
  8. `Complete job`: success

Ou seja: **as duas suítes atingem exit 0 no Linux**. A seção seguinte documenta por que elas
não atingem exit 0 *nesta máquina macOS*, e prova que a causa é o host, não a mudança.

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
canônico para estes dois arquivos é o CI Linux, que está verde — as duas correções são
conveniência de desenvolvimento em macOS, não requisito de aceite.

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
