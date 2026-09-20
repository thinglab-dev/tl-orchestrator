id: T035
title: Local Dev Distribution and Consumer Sync
type: feat
deliverable: package
standalone: true
method: native
status: ready
state_revision: 0
depends_on: [T034]
blocked_by: []
origin: decisão do maintainer em 2026-09-20 para eliminar a dependência do GitHub ao sincronizar, na mesma máquina, consumers do TL-Orchestrator durante desenvolvimento local.
decisions: []
spec_author: orchestrator
spec_revision: 1
rework_round: 0
affects_context: [distribution, project_configuration, execution_protocol]
effective_authors: [openai]
checker_independence: required
content_paths: [scripts/tl_orc.py, README.md, SKILL.md, CHANGELOG.md, distribution-manifest.json, docs/PROJECT_CONFIGURATION.md, docs/EVOLUTION.md, docs/EXECUTION_PROTOCOL.md, prompts/orchestrator.md, prompts/orchestrator-playbook.md, scripts/tests/test_tl_orc.py, scripts/tests/test_release_guardrails.py, _tl-orc/project/STATUS.md]

## Finding
source: uso real do maintainer com múltiplos consumers irmãos (`lynvia`, `platform`, `tl-auth`, `tl-aaa`) e o repositório fonte local em desenvolvimento.
observed: o perfil de instalação atual assume GitHub/release como caminho principal de atualização. Isso é adequado para publicação, mas cria atrito e risco de drift quando vários consumers da mesma máquina precisam acompanhar um commit local já validado do repositório fonte.
expected: GitHub permanece canal de publicação/colaboração; desenvolvimento local usa um comando `tl-orc` instalado no PATH para registrar consumers, sincronizar o pacote canônico e verificar todos contra um commit local identificado.
impact: reduz cópias manuais, elimina dependência de publicação para testar consumers locais e preserva o repositório TL-Orchestrator como única fonte da verdade.

## Spec
### Acceptance criteria
- AC01: adicionar `scripts/tl_orc.py` com CLI de biblioteca padrão e comandos mínimos `status`, `consumers`, `register`, `unregister`, `sync`, `verify`, `smoke` e `install-cli`; sem daemon ou serviço persistente.
- AC02: `install-cli` instala um launcher `tl-orc` no PATH local apontando para a fonte canônica configurada, sem duplicar a implementação; configuração/registry ficam fora dos repositórios em diretório de configuração do usuário.
- AC03: registry guarda nome e raiz absoluta dos consumers localmente; nenhum caminho privado é gravado no pacote distribuído ou no `INSTALLATION.md` versionável do consumer.
- AC04: `sync --all` usa exclusivamente um commit identificado do checkout fonte, recusa source dirty por padrão e valida `distribution-manifest.json` antes de qualquer mutação.
- AC05: cada consumer é atualizado somente nos destinos registrados do TL-Orc (`_tl-orc/package`, `.agents/skills/tl-orchestrator`, `.claude/skills/tl-orchestrator` quando presentes/registrados), preservando `_tl-orc/project`, specs, batches, evidências e qualquer outro conteúdo do projeto.
- AC06: antes de substituir um destino, detectar arquivo adicional/ausente/modificado em relação ao `INSTALLATION.md` vigente; delta local não autorizado bloqueia aquele consumer fail-closed, sem apagá-lo.
- AC07: sincronização por consumer usa staging verificado e troca com rollback local; falha em um consumer é reportada e não é normalizada silenciosamente como sucesso.
- AC08: após cópia, todos os arquivos do manifesto são comparados byte a byte/hash com a origem; `INSTALLATION.md` registra commit exato, `installed_version` (tag exata ou `none`), contagem/hashes, `source_mode: local-dev` e integrações sincronizadas, sem depender de acesso ao GitHub.
- AC09: `verify --all` é read-only e prova commit registrado, contagem, hashes e igualdade dos destinos; `smoke --all` é read-only e acrescenta parse/import/CLI help seguro dos scripts críticos sem escrever no consumer.
- AC10: o modo release/GitHub continua suportado pelo contrato de evolução; `local-dev` é um canal adicional, não substitui tags/releases para distribuição externa.
- AC11: regra normativa de fechamento: para `fix` ou `feat` distribuível no repositório fonte, depois de commit identificado + gates exigidos verdes, o Orquestrador executa `tl-orc sync --all` e `tl-orc smoke --all` antes de declarar fechamento local; nunca sincronizar automaticamente working tree dirty nem por hook cego de `git commit`.
- AC12: testes offline cobrem registry, source dirty, manifesto inválido, consumer com delta local, staging/rollback, atualização de 2+ consumers, verificação, smoke e preservação de `_tl-orc/project`.

### Verification
- `python3 -m unittest -v scripts.tests.test_tl_orc`
- `python3 -m unittest discover -s scripts/tests -q`
- `python3 -m unittest discover -s tests -q`
- `python3 scripts/validate_repository.py`
- `python3 scripts/audit_lineage.py`
- `git diff --check`

## Evidence
Ainda não executada. Implementação deve preservar a política upstream-first e ser revisada por Checker independente de família não-OpenAI.
