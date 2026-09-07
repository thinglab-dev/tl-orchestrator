id: T010
type: fix
deliverable: none
standalone: true
method: native
status: done
state_revision: 6
depends_on: [T009]
blocked_by: []
origin: user (2026-09-07, durante T009: "se for necessário, salva no prompt do orchestrator")
decisions: []
spec_author: orchestrator
spec_revision: 8ecaf0f6b411ac26 (s2; s1 eb1c10c039d4d8e6 revisada e aprovada em r02; ampliação de AC02 por T009-c01)
rework_round: 2
affects_context: []
content_paths: [prompts/orchestrator.md, prompts/orchestrator-perfis.md, prompts/orchestrator-playbook.md, prompts/checker-report-only.md, CHANGELOG.md]
content_id: 0de10d60149cf7c038a0954c6aec302c9fcd111e:bea29257fea4b474
worktree: branch fix/t010-conduction-rules em árvore dedicada (um escritor por árvore; T009 segue na branch analysis/t009-semantic-validation)

## Finding
source: condução de T005 e T009 no fonte e da adoção v0.5.0 no consumidor platform (evidências T009-r01..r04, T009-classification.md, tl-orchestrator-v0.5.0-working-tree-*-r01.md do platform)
observed: (1) cinco retrabalhos consecutivos em T009 corrigiram manifestações de três classes recorrentes (origem das entradas, validação, resolução do despacho) sem que o contrato mandasse parar para diagnóstico; (2) briefings do Classificador e do Checker aceitam "origem" como qualquer arquivo existente, sem distinguir o tipo de informação (política autorizada, solicitação/spec, runs efetivos, registros de evidência); (3) provas mecânicas (hash de vinculação, frase de custo em cartão) foram lidas como prova de correção ou de pertinência; (4) o Checker Astra leu ../platform fora da raiz consumidora em todas as rodadas de T009, sem autorização explícita, e o Agy fez `find` no diretório do usuário no fresh load (T008)
expected: o contrato deve (a) prever, após N retrabalhos com defeitos centrais da mesma classe, uma fase consultiva classificada que responda se são manifestações do mesmo problema ou requisitos a consolidar antes de novo rework; (b) exigir origem por tipo de informação nos briefings: catálogo e pins da política autorizada; tarefa, story_id, fase e papéis da solicitação/spec; autoria efetiva e disponibilidade dos runs efetivos; evidências dos registros identificados; (c) declarar o limite das provas mecânicas: vinculação não é correção, custo em cartão não é pertinência ao workload; (d) confinar a leitura de Checker e demais papéis à raiz consumidora e ao pacote, salvo fontes explicitamente autorizadas no briefing, com desvio declarado no parecer
impact: ciclos de retrabalho sem convergência; conformidade tautológica nos briefings; leitura de projetos alheios sem autorização
hypothesis: ausência de regra de escalonamento e de tipagem da origem em "Briefing concreto" (perfis) e em "Revisão externa" (playbook); o contrato do Checker não delimita escopo de leitura
next verification: redigir as quatro regras em orchestrator.md (regra normativa), perfis (Briefing concreto: origem por tipo; Fallback: escalonamento consultivo após N retrabalhos, N definido pelo consumidor com padrão 3), playbook (Revisão externa: limites das provas mecânicas) e checker-report-only.md (escopo de leitura); sonda contrafactual por leitura: briefing com origem genérica deve ser rejeitado pelo texto; Checker de família distinta; release menor
dedup: T007 (saída vazia) e T008 (descoberta na ativação) tratam de casos específicos; T009 (analysis) fundamenta (b) e (c); esta Task é a consolidação normativa. Implementação após o fechamento de T009, autorizada pelo usuário em 2026-09-07 ("se for necessário, salva no prompt do orchestrator")

## Spec
### Intent
Consolidar no contrato distribuído quatro regras de condução observadas como lacunas em T005, T009 e na adoção v0.5.0: escalonamento consultivo após retrabalhos recorrentes com defeitos centrais da mesma classe; origem por tipo de informação nos briefings de Classificador e Checker; limite declarado das provas mecânicas; escopo de leitura dos papéis confinado à raiz consumidora e ao pacote salvo fontes explicitamente autorizadas. Texto normativo único por assunto; sem mudar schemas nem manifesto.
### Scope and write paths
Somente: `prompts/orchestrator.md`, `prompts/orchestrator-perfis.md`, `prompts/orchestrator-playbook.md`, `prompts/checker-report-only.md`, `CHANGELOG.md` (Unreleased). Proibido qualquer outro arquivo.
### Acceptance criteria
AC01 Escalonamento: em `orchestrator-perfis.md#fallback-e-interrupção` (ou seção própria), regra de que após N rodadas de rework (padrão 3; o consumidor pode fixar outro N em PROJECT.md) com achados centrais da mesma classe, o Orquestrador classifica uma fase consultiva e despacha um consultor com a pergunta "manifestações do mesmo problema ou requisitos a consolidar?", consolidando a orientação antes de classificar novo rework; correções delimitadas seguem o fluxo normal.
AC02 Origem por tipo e conteúdo: em `orchestrator-perfis.md#briefing-concreto`, cada informação do briefing declara a fonte do seu tipo E o conteúdo dessa fonte sustenta o valor declarado, conforme tabela normativa: `story_id`, fase e papéis solicitados → solicitação/spec da Task ou fase, cujo registro citado contém o valor literal; catálogo (harness/modelo/effort), pins e cadeias → política autorizada do consumidor (PROJECT.md), cuja tabela ou seção cita exatamente o par, o pin ou a cadeia; autoria efetiva e famílias → registro de `Agent runs` efetivo, cuja linha citada declara harness, modelo e família usados; evidências de custo e capacidade → `docs/MODEL_ROUTING.md`, com pertinência ao modelo e, para proxy, afirmação de custo por tarefa; medição local → linha de tabela estruturada em evidência do projeto, com o ID na primeira coluna; julgamento → registro documental vinculado por hash ao objeto e às entradas, com veredito explícito. Localização que resolve (arquivo existe, âncora resolve, linha existe) não basta; fonte existente mas incompatível com o tipo ou com o valor é rejeitada. Lista composta na hora ou fonte genérica não vale como origem; o Classificador só recebe IDs com origem. (Ampliado em 2026-09-07 pela orientação consolidada em T009-c01.)
AC03 Limite das provas mecânicas: em `orchestrator-playbook.md#revisão-externa` (ou `#conferir-a-entrega`), frase normativa de que conferência mecânica e vinculação por hash comprovam correspondência e integridade, não correção nem pertinência; pertinência ao workload, adequação do esforço e alcance econômico permanecem julgamento registrado.
AC04 Escopo de leitura: em `checker-report-only.md` e na regra geral de `orchestrator.md`, os papéis leem somente a raiz consumidora e a raiz do pacote; qualquer outra fonte precisa constar explicitamente no briefing; leitura fora desse escopo é desvio a declarar no parecer ou relatório.
AC05 Coerência: nenhuma contradição com reclassificação por fase, independência (preferred/required), regra de que o Orquestrador nunca escolhe modelo/effort, e com o escopo de T007/T008 (que permanecem separadas); SKILL.md e demais arquivos só remetem.
AC06 Portões: validador verde; manifesto e schemas inalterados; CHANGELOG em Unreleased sem menção a ferramenta ou autoria; sondas por leitura: (a) briefing com origem genérica → o texto o rejeita; (b) quarto rework com achado da mesma classe → o texto manda escalar; (c) Checker que leu fora da raiz sem autorização → o texto manda declarar desvio.
### Verification profile
`fix` de texto normativo: sondas contrafactuais por leitura (AC06) e Checker report-only de família distinta de toda autoria efetiva, com hipótese rejeitada por critério.
## Result
Quatro regras consolidadas no contrato distribuído: escalonamento consultivo após N reworks (`orchestrator-perfis.md`, Fallback e interrupção); origem por tipo e conteúdo com tabela normativa de seis tipos (`orchestrator-perfis.md`, Briefing concreto); limite das provas mecânicas (`orchestrator-playbook.md`, Revisão externa); escopo de leitura confinado (`orchestrator.md`, invariantes; `checker-report-only.md`). CHANGELOG em Unreleased. Texto único por assunto com remissões.

## Evidence
`evidence/T010-classification.md`, `T010-maker-report.md`, `T010-r01.md` (changes_requested, duplicação), `T010-r02.md` (approved, spec s1), `T010-r03.md` (approved, spec s2 com a tabela de procedência).

## Review
r01 changes_requested → rework 1; r02 approved (s1); spec ampliada para s2 por T009-c01; r03 approved (Checker codex gpt-6-astra high, run T010-r03-checker-1), com desvio de leitura autodeclarado pelo Checker (metadados Git via gitdir do worktree). `done` em 20260907T231408Z após o fechamento de T009 (depends_on satisfeito); conteúdo distribuído publicado no PR #26 sem merge. 20260907T230926Z.
