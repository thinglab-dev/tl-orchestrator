id: T004
type: fix
deliverable: none
standalone: true
method: native
status: done
state_revision: 3
depends_on: []
blocked_by: []
origin: user (2026-09-07, durante lynvia-mkauth-connector:T004 no platform)
decisions: []
spec_author: orchestrator
spec_revision: s1
rework_round: 1
affects_context: []
content_paths: [prompts/orchestrator.md, prompts/orchestrator-perfis.md, SKILL.md, CHANGELOG.md]
content_id: 3d433d7cdb64fa778d07ad3cada38c303af94d23:3c36b7f85fac9e50

## Finding
source: condução de T004 no platform em 2026-09-07
observed: o Orquestrador fixou o modelo do Checker por suposição (sonnet, depois opus) e só depois usou o Classificador; o contrato exige classificar antes de despachar e diz que pins não dispensam a chamada, mas não proíbe explicitamente que o Orquestrador escolha modelo/effort por conta própria nem define quando uma preferência vira pin
impact: dimensionamento por palpite, custo e capacidade fora do catálogo, e violação silenciosa da regra de classificação
next verification: smoke de triagem onde o usuário sugere "use Claude" sem modelo: o Orquestrador deve classificar e despachar o par recomendado, sem fixar modelo

## Spec
### Intent
Tornar explícito, no contrato do Orquestrador, nos perfis e no SKILL.md, que antes de despachar Planner, Maker ou Checker em qualquer fase (debate, planning, implementation, review, rework) o Orquestrador sempre obtém e valida uma classificação; que ele nunca escolhe modelo ou effort por conta própria, por sugestão ou por conveniência; que só uma escolha explícita do usuário ou do consumidor, com modelo nomeado, vira pin, e mesmo assim o Classificador é chamado com o pin como restrição; que a família independente do Checker é restrição de entrada, não escolha de modelo.
### Scope and write paths
prompts/orchestrator.md, prompts/orchestrator-perfis.md, SKILL.md, CHANGELOG.md.
### Acceptance criteria
AC01 texto normativo único por assunto, sem duplicar mecânica; AC02 nenhuma contradição com a regra de reclassificação por fase e com a política de independência; AC03 validador do repositório verde; AC04 sonda contrafactual: um briefing sintético "prefiro Claude no Checker" sem modelo deve resultar em classificação com família restrita e modelo escolhido pelo Classificador, não em pin de modelo.
### Verification profile
docs com garantia comportamental do método: sonda por leitura do texto novo (contraprova a e b) e Checker de família distinta.

## Result
Regra normativa única em `prompts/orchestrator.md#perfil-padrão-de-despacho`: o Orquestrador nunca escolhe modelo ou effort de Planner, Maker ou Checker por conta própria, por sugestão ou por conveniência; classifica em toda fase antes do primeiro despacho de cada papel; preferência de harness ou família é restrição de entrada do Classificador; só um modelo nomeado explicitamente pelo usuário ou pelo consumidor vira pin, e mesmo assim o Classificador é chamado com o pin como restrição; a independência de família do Checker é restrição de entrada. `prompts/orchestrator-perfis.md` e `SKILL.md` remetem à regra sem repetir a mecânica. CHANGELOG em Unreleased, cortado na 0.4.1.

## Evidence
`evidence/T004-r01.md` (changes_requested: R1 duplicação em três fontes; R2 limitação do validador no sandbox), `evidence/T004-r02.md` (approved). Sonda AC04 (a) e (b) confirmada pelo Checker por leitura das frases decisivas.

## Review
r01 `changes_requested` → rework (dedup); r02 `approved`, Codex gpt-5.6-terra high, sem ações. Fechada em 20260907T152540Z.
