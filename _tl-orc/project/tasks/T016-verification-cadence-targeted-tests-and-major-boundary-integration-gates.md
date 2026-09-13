id: T016
type: gov
deliverable: none
standalone: true
method: native
status: done
state_revision: 2
depends_on: [T022]
blocked_by: []
origin: instrução normativa do mantenedor em 2026-09-12 (formalização da política de cadência de verificação e portões de integração)
decisions: []
spec_author: orchestrator
spec_revision: c484a2267d584504
rework_round: 0
affects_context: []
content_paths: [docs/WORK_MODEL.md, prompts/orchestrator.md, prompts/orchestrator-playbook.md, prompts/checker-report-only.md, docs/PROJECT_CONFIGURATION.md, scripts/tests/test_verification_cadence.py, CHANGELOG.md]
content_id: 240e0396a3377a319ae8b4604cf91104e21418c7:a22d4dce095d723e

## Finding
source: alinhamento estratégico e análise de custo e latência operacional durante os ciclos do Epic 6 e Tasks nativas T011–T015 em 2026-09-12
observed: o contrato do tl-orchestrator enfatiza a obrigatoriedade de portões executados na árvore final, mas não distingue adequadamente entre a verificação direcionada da unidade (local targeted verification) e o portão global de integração (canonical full integration gate). Isso levou a execuções redundantes de suítes de teste completas (como make check no platform) a cada Story, substory, rodada de rework documental ou avaliação de Checker dentro de um mesmo bloco, gerando desperdício desnecessário de tempo, CPU e turnos de modelo.
expected: formalizar contratualmente no núcleo do método o princípio "targeted early and throughout → canonical full integration gate only at major boundary". O portão completo de integração pertence ao bloco/fronteira principal, e não à Story individual. Dentro de um mesmo grupo de integração, a verificação deve ser estritamente direcionada ao diff, aos consumidores afetados, aos ACs e às sondas contrafactuais. O portão global canônico deve ser exigido apenas imediatamente antes da transição para um novo grupo principal, bloqueando a transição se não terminar verde.
impact: reduz drasticamente tempo de ciclo, consumo computacional e turnos redundantes sem enfraquecer o rigor da prova, substituindo repetições mecânicas de suítes globais por cobertura localizada contínua somada a uma integração global no ponto em que ela efetivamente tem valor.
hypothesis: a generalização agnóstica dessa cadência em docs/WORK_MODEL.md, prompts/orchestrator.md, prompts/orchestrator-playbook.md, prompts/checker-report-only.md, docs/PROJECT_CONFIGURATION.md e suíte de testes determinísticos previne tanto o excesso de testes quanto falsos apontamentos de deficiência por Checkers, mantendo total flexibilidade para projetos em Go, Rust, Node, Python, etc.
dedup: T010 fixou limites de condução e escalonamento; T013 tratou de esperas, liveness e lote autorizado; T014 formalizou a política global de participantes; T015 tratou de context economy e selective retrieval; T016 normatiza a cadência de verificação e os portões de fronteira de integração.

## Spec
### Intent
Normatizar a política de cadência de testes no tl-orchestrator, estabelecendo que unidades de trabalho dentro de um mesmo grupo de integração executam exclusivamente verificações direcionadas ao seu escopo alterado e aos seus critérios de aceitação, reservando a execução do portão global canônico de integração para a fronteira de fechamento do grupo (imediatamente antes da transição para o próximo bloco). A regra deve ser universal, desacoplada de comandos específicos (como make check) e desacoplada de convenções sintáticas de ID (resolvendo o agrupamento através da autoridade do trabalho: Epic no BMAD, Deliverable no Native, Native Standalone Task como seu próprio grupo quando sem Deliverable ou grupo explícito, ou grupo explícito declarado de integração). O Orquestrador nunca infere comandos de full gate não configurados (registrando not_configured e bloqueando transições de fronteira até resolução), e reaproveitamentos de prova de CI exigem identidade de commit e paridade da definição/revisão do gate.

### Scope and write paths
- docs/WORK_MODEL.md: formalização dos conceitos de targeted verification vs. canonical full integration gate, regras de transição de fronteira, regime estrito de exceções e cláusula de invalidação por alteração da árvore.
- prompts/orchestrator.md e prompts/orchestrator-playbook.md: instruções operacionais para seleção do perfil de teste e momento de invocação do portão canônico.
- prompts/checker-report-only.md: instrução mandatória ao Checker proibindo apontamento de deficiência pela ausência de full gate rotineiro dentro do mesmo grupo, orientando auditoria baseada no metadado verification_scope: targeted | integration_boundary | exceptional_full.
- docs/PROJECT_CONFIGURATION.md: parametrização agnóstica de canonical_full_gate e verification_cadence.
- scripts/tests/test_verification_cadence.py: suíte de testes determinísticos validando as invariantes normativas e sondas de decisão.
- CHANGELOG.md: registro formal da nova política na distribuição.

### Acceptance criteria
AC01 (Targeted Verification Intragrupo): Dentro do mesmo integration group (Epic no BMAD, Deliverable no Native ou agrupamento equivalente declarado), as etapas de implementação, revisão e rework utilizam estritamente testes direcionados ao diff, aos pacotes/módulos alterados, aos consumidores diretos, aos ACs específicos e a sondas contrafactuais.
AC02 (Checker Alinhado à Cadência): O Checker independente é instruído explicitamente a avaliar a suficiência dos testes direcionados; a ausência de execução de full gate dentro do grupo não pode ser apontada como deficiência de evidência ou bloqueio de aprovação. O briefing de revisão inclui o campo verification_scope: targeted | integration_boundary | exceptional_full.
AC03 (Rework Econômico e Focado): Em ciclos de changes_requested, a re-execução de testes restringe-se estritamente ao patch alterado, aos consumidores impactados e aos ACs relacionados. Reworks estritamente documentais, de evidência, de metadados ou de status não executam testes funcionais, admitindo no máximo verificações textuais (git diff --check, lint estrutural).
AC04 (Full Gate na Fronteira Principal): O portão completo canônico de integração (canonical_full_gate) é disparado obrigatoriamente e exclusivamente no fechamento da unidade final de um grupo principal, imediatamente antes de autorizar a transição para o próximo grupo (ex.: fechamento de Epic 6 antes de abrir Epic 7). O canonical_full_gate precisa terminar verde; falha bloqueia a transição para o próximo integration group.
AC05 (Invalidação Estrita da Árvore): O resultado de um canonical_full_gate é rigorosamente vinculado à revisão específica da árvore (commit SHA). Qualquer modificação de código posterior dentro do grupo invalida a prova do gate e exige nova execução antes da transição de fronteira.
AC06 (Regime Restrito de Exceção Antecipada): A execução de um full gate antecipado dentro do grupo é excepcional e restrita a mudanças estruturais transversais (ex.: migração de esquema de banco compartilhado, alteração de protocolo cross-módulo, mudança em primitivas globais de concorrência ou no sistema de build).
AC07 (Rejeição de Justificativas Genéricas): Toda exceção antecipada exige bloco formal de metadados (full_gate_exception) detalhando razão técnica objetiva e justificativa de por que os testes direcionados seriam insuficientes. Termos genéricos como "por segurança", "para garantir tudo" ou "para confirmar" são explicitamente inválidos e rejeitados.
AC08 (Reaproveitamento de Prova de CI): Quando o pipeline de CI externo (ex.: GitHub Actions) já executou com sucesso o canonical_full_gate sobre o mesmo commit exato da árvore e sob a mesma definição/revisão do gate, com logs auditáveis, o Orquestrador pode reutilizar essa prova, sendo proibido duplicar a execução completa local sem justificativa técnica. Caso o comando, configuração ou definição do gate tenha sido alterado após a execução do CI, a prova anterior é nula e a verificação deve ser refeita.
AC09 (Resolução por Autoridade, sem Regex de ID, e Caso Standalone): A identificação do grupo de integração é resolvida semanticamente pela autoridade do trabalho (campo epic em itens BMAD, campo deliverable em Tasks Native, ou configuração de mapeamento no projeto consumidor), sendo expressamente vedado o parsing ad hoc de convenções de nomenclatura ou regex sobre o identificador da Story. Uma Native Standalone Task sem Deliverable e sem integration_group explícito constitui seu próprio integration_group (authority: native_standalone, id: <Task_ID>), e o portão canônico de fronteira é exigido ao fechar esse grupo antes de iniciar outro grupo independente.
AC10 (Comando Canônico Parametrizável e Vedação a Suposições): O método trata o comando do portão global como canonical_full_gate configurável pelo consumidor (ex.: make check, cargo test --workspace, npm test, go test ./..., pytest), sem acoplamento a ferramentas específicas do projeto platform. O Orquestrador é expressamente proibido de inferir ou adivinhar comandos de full gate não configurados; se o consumidor não possuir um full gate explicitamente configurado ou derivável de política existente, deve registrar canonical_full_gate: not_configured, tratando isso como pendência bloqueante antes de qualquer transição que exija o portão.
AC11 (Suíte Contratual Determinística): Criação de testes determinísticos em scripts/tests/test_verification_cadence.py validando todas as transições de estado, aceitação/rejeição de justificativas de exceção, vínculo de commit e identificação por autoridade.
AC12 (Validação e Consistência do Repositório): Suíte estrutural python3 scripts/validate_repository.py com exit 0, garantindo integridade de links, manifesto e documentação.

### Verification profile
gov / feat: execução da suíte contratual determinística test_verification_cadence.py (exit 0), validate_repository.py (exit 0) e auditoria de Checker independente (família elegível conforme autoria).

### Condições para promover a ready
1. ✅ Finding, Intent, Scope, os 12 ACs e Verification profile aprovados pelo mantenedor em 2026-09-12.
2. ✅ T015 (Context Economy) concluída e aprovada (done).
3. ➖ Implementação, chamadas a agentes e alteração nos contratos: dependem de autorização explícita posterior.

## Result
Implementação concluída com sucesso no commit `cccc144e0cc717deb72e30d0b041bc527fbfc3cf` (+780 / -9 linhas) abrangendo exatamente os 7 `content_paths`:
1. `docs/WORK_MODEL.md`: formalização da cadência de verificação ("targeted early and throughout → canonical full integration gate only at major boundary"), portões de fronteira de integração, resolução de grupo por autoridade sem regex, tratamento de Native Standalone Task como integration group próprio, regime estrito de exceções com rejeição de justificativas genéricas, regras de reaproveitamento de CI e tratamento de `canonical_full_gate: not_configured`.
2. `prompts/orchestrator.md`: inclusão do invariante de cadência de verificação e momento do canonical full gate.
3. `prompts/orchestrator-playbook.md`: diretrizes de orquestração sob `verification_scope`, resolução de grupo, bloqueio por `not_configured` e formato do briefing do Checker.
4. `prompts/checker-report-only.md`: instrução mandatória proibindo apontar ausência de full gate rotineiro sob escopo targeted, auditoria orientada a `verification_scope`.
5. `docs/PROJECT_CONFIGURATION.md`: parametrização agnóstica de `canonical_full_gate` e `verification_cadence`.
6. `scripts/tests/test_verification_cadence.py`: nova suíte com 25 testes contratuais determinísticos cobrindo integralmente AC01–AC12.
7. `CHANGELOG.md`: documentação completa das novas diretrizes de cadência na distribuição.

## Evidence
- Arquivo de evidência consolidado: [_tl-orc/project/evidence/T016-r01.md](file:///Users/albertiano/thinglab/tl-orchestrator/_tl-orc/project/evidence/T016-r01.md).
- Target commit: `cccc144e0cc717deb72e30d0b041bc527fbfc3cf`.
- Base commit: `240e0396a3377a319ae8b4604cf91104e21418c7`.
- Content ID canônico: `240e0396a3377a319ae8b4604cf91104e21418c7:a22d4dce095d723e`.
- Prova direcionada: `python3 -B -m unittest scripts/tests/test_verification_cadence.py` (25/25 testes, exit 0).
- Prova suplementar de integração: `python3 -B -m unittest discover -s scripts/tests -p "test_*.py"` (79/79 testes, exit 0).
- Portão canônico completo de integração (`canonical_full_gate`): `python3 scripts/validate_repository.py` na raiz (exit 0).
- Consumo orçamentário: 4 chamadas a modelos (Classifier impl, Maker impl, Classifier review, Checker final).

## Review
- Artefatos de revisão: [_tl-orc/project/evidence/T016-r01/review/](file:///Users/albertiano/thinglab/tl-orchestrator/_tl-orc/project/evidence/T016-r01/review/).
- Checker independente: OpenAI Codex `gpt-5.6-terra/high` (sessão `01a0964e-cad8-7e30-9200-abf8949df2cd`), fresh session, report-only.
- Independência: `product_checker_independence: full_cross_family` (Maker Google Gemini 3.8 Flash High vs. Checker OpenAI Codex Terra High).
- Parecer estruturado: `approved` (0 action items, 0 deferred, 6 hipóteses rejeitadas com fundamentação nos contratos normativos).
