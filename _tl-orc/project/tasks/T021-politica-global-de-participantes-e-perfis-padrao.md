id: T021
type: feat
deliverable: none
standalone: true
method: native
status: done
state_revision: 2
depends_on: [T020]
blocked_by: []
origin: solicitação do usuário em 2026-09-11 (formalização de política global de participantes)
decisions: []
spec_author: orchestrator
spec_revision: 3462d25f16aba270
rework_round: 1
affects_context: []
content_paths: [prompts/orchestrator-perfis.md, README.md, _tl-orc/PROJECT.md, CHANGELOG.md, prompts/orchestrator.md, docs/PROJECT_CONFIGURATION.md, _tl-orc/project/evidence/T014-participant-policy-tests.py]
content_id: b06d37e3cca2f9f4507287c3ee25e7437db47f18:92af1197adf79c80

## Finding
source: alinhamento estratégico de governança e cotas operacionais de 2026-09-11
observed: o perfil-padrão publicado anteriormente definia Maker Codex e Checker Agy, enquanto este repositório fonte usava Agy Maker por preferência e Codex Checker pelo piloto Astra; além disso, projetos consumidores (como platform) duplicavam tabelas locais inteiras e retinham pins rígidos (como gpt-6-astra compulsório), gerando risco de fontes concorrentes de verdade e pressão desbalanceada sobre cotas do Codex.
expected: unificar a política padrão publicada para que qualquer projeto com Agy, Claude e Codex herde por omissão a distribuição equilibrada (Gemini para volume em Classifier, Maker e Searcher; Claude para Planner; Codex Terra High para Checker independente de alto valor), submetendo a cadeia nominal à autoria efetiva e permitindo herança limpa nos consumidores sem duplicação.
impact: elimina disparidades entre fonte e consumidores, preserva cotas do Codex para auditoria de alto valor, poupa modelos restritos de carga pesada e garante governança reproduzível.
hypothesis: a atualização dos perfis publicados, do README, do catálogo do projeto e a adição de testes determinísticos consolida o arranjo sem quebrar os 17 arquivos do manifesto.
next verification: execução de `T014-participant-policy-tests.py` e `validate_repository.py`.
dedup: T003/T004 trataram de avanço da cadeia do Classificador; T010 tratou de limites de condução; T014 formaliza a política global de participantes.

## Spec
### Intent
Consolidar e publicar a política global padrão de participantes e cadeias do tl-orchestrator para projetos com os três harnesses (Agy, Claude e Codex) disponíveis, estabelecendo a divisão econômica de carga (Gemini para alto volume de Classificador, Maker e Searcher; Claude para Planner; Codex Terra High para Checker independente de alto valor), desvinculando pins rígidos do Astra, garantindo a subordinação estrita do Checker à autoria efetiva completa, fixando a precedência normativa (usuário > projeto > default publicado) e formalizando o modelo de herança limpa pelos projetos consumidores sem duplicação de tabelas.

### Scope and write paths
Somente: `prompts/orchestrator-perfis.md`, `README.md`, `_tl-orc/PROJECT.md`, `CHANGELOG.md` e `_tl-orc/project/evidence/T014-participant-policy-tests.py`.

### Acceptance criteria
AC01 Perfil-padrão publicado em `prompts/orchestrator-perfis.md`:
  - Atualizar a tabela de preferência em `#perfil-padrão` para Maker: Agy → Codex → Claude e Checker report-only: Codex → Claude → Agy.
  - Detalhar pares modelo/effort por papel: Classifier Agy Flash Medium / Codex Luna / Claude Sonnet; Planner Claude Sonnet / Codex Terra / Agy Gemini; Maker Agy Flash High / Codex Terra / Claude Sonnet; Checker Codex Terra High / Claude Sonnet/Opus / Agy Gemini.
  - Fixar a subordinação estrita da ordem nominal do Checker à autoria efetiva completa (incluindo Orquestrador, Maker e reworks).
  - Formalizar a precedência normativa: usuário > projeto local > perfil publicado.
  - Declarar a herança limpa por projetos consumidores, dispensando duplicação redundante de tabelas locais.

AC02 Espelhamento no `README.md`:
  - Atualizar o item 6 do Quick Start com as cadeias de Maker Agy e Checker Codex, e menção à herança por omissão.

AC03 Alinhamento do `_tl-orc/PROJECT.md`:
  - Catálogo de Checker ajustado com `gpt-5.6-terra/high` como referência padrão prioritária e desvinculação do pin obrigatório do Astra (mantido como candidato experimental para testes).

AC04 Registro no `CHANGELOG.md`:
  - Entradas documentadas sob `## [Unreleased]` em `### Adicionado` e `### Alterado`.

AC05 Suíte determinística em `_tl-orc/project/evidence/T014-participant-policy-tests.py`:
  - Script determinístico contendo asserções das 5 invariantes textuais e 6 sondas de decisão funcional (prioridade nominal dos 4 papéis, fallback por ausência de harness, Maker Google -> Checker Codex, Google+OpenAI -> Checker Claude, bloqueio de auto-revisão sob required e precedência de overrides).
  - Execução com exit 0.

AC06 Portão estrutural:
  - `python3 scripts/validate_repository.py` exit 0 (17 arquivos de pacote, links e hashes validados).

### Verification profile
`feat`: conferência mecânica via `_tl-orc/project/evidence/T014-participant-policy-tests.py` (exit 0), validador estrutural do repositório exit 0 e revisão independente posterior.

## Result
Implementação da política global padrão de participantes e perfis concluída em prompts/orchestrator-perfis.md, README.md, prompts/orchestrator.md, docs/PROJECT_CONFIGURATION.md, _tl-orc/PROJECT.md e CHANGELOG.md; validada deterministicamente pela suíte _tl-orc/project/evidence/T014-participant-policy-tests.py (5 invariantes e 6 sondas funcionais com exit 0) e scripts/validate_repository.py (exit 0).

## Evidence
`_tl-orc/project/evidence/T014-participant-policy-tests.py`, `_tl-orc/project/evidence/T014-r01.md`.

## Review
Rodada r01: Classificador Agy gemini-3.8-flash-medium classificou tier heavy; Checker independente OpenAI Codex gpt-5.6-terra em esforço high emitiu parecer changes_requested com 1 action item de patch (R1: inconsistência legada de cadeias em README.md:11 e no diagrama Mermaid em README.md:282, 285). Correção de R1 implementada e validada deterministicamente com 0 chamadas adicionais.
Ratificação final: Mantenedor ratificou diretamente o saneamento mecânico de R1 em 2026-09-11 (Opção 1, 0 chamadas adicionais), considerando as provas determinísticas (T014-participant-policy-tests.py e validate_repository.py com exit 0) e a sincronização do pacote com platform suficientes para fechamento como done.
