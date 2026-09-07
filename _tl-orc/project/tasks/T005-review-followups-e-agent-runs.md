id: T005
type: feat
deliverable: none
standalone: true
method: native
status: done
state_revision: 4
depends_on: [T004]
blocked_by: []
origin: user (autorização de implementação em 2026-09-07; spec congelada em docs/specs/review-followups.md revisão 1, PR #18)
decisions: []
spec_author: orchestrator
spec_revision: 161fd40618acda27
rework_round: 2
affects_context: []
content_paths: [prompts/orchestrator-perfis.md, docs/WORK_MODEL.md, prompts/orchestrator-playbook.md, SKILL.md, docs/PROJECT_CONFIGURATION.md, CHANGELOG.md]
content_id: 7923d9c22d1c4fe74cf07049e61810db0f36a14f:2f69fcb3080a395d

## Spec
### Intent
Implementar a especificação congelada `docs/specs/review-followups.md` (revisão 1) no método distribuído: pendência de revisão por outra família como fonte oficial na evidência da unidade, estados `pending`/`superseded`/`closed` com substituta vinculada e mapeamento de garantias, identidade completa da unidade (§3) compatível com BMAD multiárea, registro uniforme `Agent runs` com `run_id`, disponibilidade comprovada pela chamada normal (§8), revisão posterior sem autorização automática de correção (§6), `review_followups` no cabeçalho global e item de menu na ativação (§7). Schemas e manifesto inalterados.
### Scope and write paths
Somente: `prompts/orchestrator-perfis.md`, `docs/WORK_MODEL.md`, `prompts/orchestrator-playbook.md`, `SKILL.md`, `docs/PROJECT_CONFIGURATION.md`, `CHANGELOG.md` (entrada em Unreleased). Proibido: `schemas/`, `distribution-manifest.json`, `README.md`, `docs/specs/`, `_tl-orc/`, qualquer outro arquivo.
### Acceptance criteria
AC01 Cobertura: cada seção normativa da spec (§3 identidade, §4 fonte oficial e bloco, §5 estados e fechamento, §6 revisão posterior e autorização, §7 STATUS e ativação, §8 disponibilidade, §9 Agent runs) implementada no arquivo previsto em §10, com tabela de cobertura seção → arquivo:linhas no relatório do Maker; texto normativo único por assunto, demais arquivos remetem por link.
AC02 Coerência: nenhuma contradição com reclassificação por fase, com a política de independência (`required` continua bloqueando; indisponibilidade nunca converte `required` em `preferred`), com o vínculo parecer→`content_id`, com a coordenação cooperativa e um escritor por árvore, e com a regra de que o Orquestrador nunca escolhe modelo/effort.
AC03 Templates: bloco `## Review follow-up` (campos de §4, incluindo `supersedes`, `locator`, `log`), tabela `Agent runs` (colunas de §9, `run_id` no formato `<unit_id>-rNN-<role>-<seq>`, identidade herdada do cabeçalho), Evidence round atualizado, `review_followups` no template do STATUS global (native e bmad), exemplos das quatro formas de identidade de §3.
AC04 Portões: `python3 scripts/validate_repository.py` verde; manifesto com 17 arquivos inalterado; schemas inalterados; todas as âncoras novas resolvem.
AC05 Sondas por leitura (citar a frase decisiva de cada): cenários 1, 2, 4, 5, 6/6b, 7, 8, 9, 10, 12 e 15 de §11 decididos pelo texto novo.
AC06 CHANGELOG em Unreleased descrevendo a capacidade, sem menção a ferramenta, sessão ou autoria operacional; nenhum caminho privado.
### Verification profile
`feat` do método: sonda contrafactual por leitura (AC05), portão do repositório (AC04) e Checker report-only de família distinta de toda autoria efetiva (piloto `gpt-6-astra/high`, restrição `required` específica desta revisão). Cenários 16–18 de §11 comprovados pela própria execução real do Checker: chamada normal como prova de disponibilidade, leitura do alvo, parecer só em JSON e associação registrada pelo Orquestrador.

## Result
Capacidade implementada nos seis arquivos distribuídos conforme `docs/specs/review-followups.md` revisão 1: identidade completa de unidade e `review_followups` no cabeçalho global (WORK_MODEL, Estado); `done` sob `preferred` com pendência aberta (WORK_MODEL, Conclusão); bloco `## RF-<unit_id>-rNN` como fonte oficial da pendência, estados `pending`/`superseded`/`closed`, substituta com `supersedes` e `reason`, `locator`, `run_id` e tabela `Agent runs` (WORK_MODEL, Registro de revisão e templates); condução da revisão posterior e o que ela autoriza (playbook, Fechamento ou interrupção); leitura de `review_followups` na preparação (playbook, Preparar); opção de menu "Revisar por outra família (n)" (SKILL.md); autoria efetiva, pendência sob `preferred`, `required` inconvertível e disponibilidade pela chamada normal (perfis); frase em PROJECT_CONFIGURATION; CHANGELOG em Unreleased. Schemas e manifesto inalterados (17 arquivos).

## Evidence
`evidence/T005-classification.md` (classificações das fases, com o desvio de validação semântica da fase implementation registrado), `evidence/T005-maker-report.md` (relatórios literais do Maker r01, rework 1 e rework 2, com as conferências do Orquestrador), `evidence/T005-r01.md` (Checker r01 changes_requested), `evidence/T005-r02.md` (Checker r02 approved). Validador verde após cada rodada.

## Review
r01 `changes_requested` (Checker codex gpt-6-astra high, run T005-r01-checker-1, evidence/T005-r01.md): R1 fonte de §6 fora do arquivo previsto pelo §10; R2 âncora do bloco de follow-up não materializada pelos templates. Rework 2 despachado ao Maker Agy gemini-3.8-flash-high.
r02 `approved` (Checker codex gpt-6-astra high, run T005-r02-checker-1, evidence/T005-r02.md), 0 ações, 14 hipóteses rejeitadas; R1 e R2 confirmados corrigidos por instanciação. Desvios do Orquestrador registrados em evidence/T005-classification.md: despacho do Maker sob classificação semanticamente inválida; reworks e review r02 sem classificação de fase. Fechada em 20260907T182157Z.
