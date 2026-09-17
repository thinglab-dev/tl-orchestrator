id: T032
title: Protocolo de Retomada Curta e Transicao entre Ciclos
type: feat
deliverable: package
standalone: true
method: native
status: draft
state_revision: 0
depends_on: [T022, T023]
blocked_by: []
origin: user (autorizacao formal em 2026-09-17 para institucionalizar as conclusoes de T023 e a base tecnica de T022)
decisions: []
spec_author: orchestrator
spec_revision: pending_freeze
rework_round: 0
affects_context: []
effective_authors: [google]
checker_independence: required
content_paths:
  - docs/WORK_MODEL.md
  - docs/EXECUTION_PROTOCOL.md
  - docs/CONTEXT_POLICY.md
  - prompts/orchestrator.md
  - prompts/orchestrator-playbook.md
  - scripts/resume_generate.py
  - scripts/context_lib.py
  - schemas/resume-manifest.schema.json
  - scripts/tests/test_resume_generate.py
  - _tl-orc/project/STATUS.md
  - _tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md

## Finding
source: conclusoes empiricas de T023 (_tl-orc/project/evidence/T023-r01.md), base tecnica de T022 (_tl-orc/project/tasks/T022-*.md / evidence/T015-r03b.md) e autorizacao do mantenedor em 2026-09-17
observed:
  1. T023 provou que a retomada em sessao limpa a partir de um Pacote Curto de Retomada como indice nao-tautologico de conferencia obrigatoria previne vicios cognitivos de historico longo e assegura 100% de aderencia a governanca, com 81,8% de cache hit de prefixo no harness.
  2. No entanto, o piloto foi um experimento delimitado (N=1 pareado sobre checkpoint adaptado T009 r02). T023 nao demonstrou nem alegou economia monetaria universal nem superioridade incondicional de contexto curto em todos os cenarios; custos de bootstrap, variacao de cache e complexidade da tarefa podem alterar a relacao economica.
  3. Hoje o metodo dispoe de ferramentas iniciais em scripts/ (resume_generate.py, context_lib.py, schemas/resume-manifest.schema.json gerados em T022), mas nao possui um primitive oficial e integrado de transicao entre ciclos no Orquestrador que produza handoff verificavel, inicie nova sessao limpa, obrigue leitura seletiva e impeca que o pacote curto adquira autoridade propria.
  4. Incompatibilidade de hashes, drift de revisoes de spec/unidade ou pacotes stale precisam de deteccao deterministica fail-closed e reconstrucao de contexto a partir das fontes oficiais.
expected:
  1. Tornar a transicao curta entre ciclos uma primitive oficial do Orchestrator: produzir um handoff verificavel e minimo, iniciar sessao limpa a partir dele, obrigar conferencia seletiva das fontes oficiais e impedir terminantemente que o resumo adquira autoridade normativa propria.
  2. Implementar a arquitetura formal de pipeline:
     Ciclo N -> Close/stable checkpoint -> Context Compiler -> Short Resume Package -> Nova sessao do Orchestrator -> Verify package mechanically -> Selective source reads -> Reconstruct minimum sufficient context -> Continue Cycle N+1.
  3. Incorporar os 10 principios normativos de T032:
     - 1. Short Resume Package e indice verificavel, nunca autoridade normativa.
     - 2. Fontes oficiais continuam sendo a unica origem da verdade.
     - 3. Toda entrada critica carrega provenance suficiente para verificacao deterministica.
     - 4. Hash/revision/content-id incompativel dispara fail-closed ou reconstrucao explicita.
     - 5. A sessao nova carrega apenas contexto minimo suficiente.
     - 6. Selective retrieval e dirigido pela tarefa atual, nao por releitura global acritica.
     - 7. Nao alegar economia universal de tokens ou custos; manter instrumentacao metrica para medicao caso a caso.
     - 8. Resume package nao transporta logs, transcricoes ou evidencias volumosas quando ponteiros verificaveis bastarem.
     - 9. Estado duravel pertence ao journal/repositorio/state store; conversa nao e banco de estado.
     - 10. O protocolo deve permitir continuidade cross-harness.
impact: confere robustez deterministica a conducao do Orquestrador, viabilizando ciclos longos de desenvolvimento sem degradacao cognitiva, sem perda de governanca e sem acumulo de contexto obsoleto.
dedup: T022 construiu a biblioteca inicial de selective retrieval e schema de manifest; T023 produziu a evidencia experimental comparativa; T032 institucionaliza o protocolo no pacote distribuido.

## Spec
### Phase A (Draft Provisorio para Freeze)
### Intent
Institucionalizar o protocolo deterministico de reconstrucao seletiva de contexto e transicao curta entre ciclos de trabalho do Orquestrador, integrando contratos, schemas, validadores de integridade pre-despacho e playbooks operacionais.

### Provisional Scope & Write Paths (Phase A)
Os caminhos abaixo sao provisorios e serao ratificados/congelados apos a consulta ao Advisor e discovery mecanico:
- `docs/WORK_MODEL.md`: secao sobre protocolo de transicao entre ciclos e ciclo de vida de contexto.
- `docs/EXECUTION_PROTOCOL.md`: interface de handoff e isolamento de sessao.
- `docs/CONTEXT_POLICY.md`: refinamento de politicas de entrega e freshness states.
- `prompts/orchestrator.md`: inclusao do primitive de handoff e inicializacao por pacote curto.
- `prompts/orchestrator-playbook.md`: procedimento operacional de geracao de handoff, abertura de sessao limpa e recuperacao de drift.
- `scripts/resume_generate.py`: extensao para compilacao de handoff completo e checagem estrita de integridade.
- `scripts/context_lib.py`: funcoes auxiliares de canonicalizacao, hash e resolucao.
- `schemas/resume-manifest.schema.json`: schema canônico do pacote de transição (Draft 2020-12).
- `scripts/tests/test_resume_generate.py`: testes unitarios e contrafactuais de fail-closed, drift e determinismo.
- `_tl-orc/project/STATUS.md`: registro de estado e coordenacao.
- `_tl-orc/project/tasks/T032-protocolo-de-retomada-curta-e-transicao-entre-ciclos.md`: especificacao congelada.

### Estrutura do Pacote Curto de Transicao (Short Resume Package)
O artefato gerado atua estritamente como **indice derivado de navegacao e atestacao**, contendo:
1. **Identidade Qualificada do Trabalho:** `active_work_ref` (<method>/<unit_type>/<id>@<source_location>), `state_revision`, `spec_revision`, `content_id`.
2. **Estado e Coordenacao:** `phase`, `effective_authors`, `open_items` (action items / deferred pendentes), `next_action`.
3. **Decisoes e Restricoes Vigentes:** digest de `PROJECT.md` e decisoes arquiteturais consolidadas aplicaveis.
4. **Fontes Oficiais Obrigatorias e Hashes:** lista canonica de arquivos com `path`, `selector` e `digest` SHA-256.
5. **Contexto Resolvido com Justificativa:** secao `resolved_context` mapeando classes para modos de entrega (`inline`, `excerpt`, `on_demand`) e razoes de leitura.
6. **Provenance e Integridade:** `generated_at`, `generator_version`, atestacao de conformidade contra o estado em disco.

### Mecanismo de Validacao Pre-Despacho (Fail-Closed)
Antes de qualquer acao na sessao limpa:
- O Orquestrador (ou script `resume_generate.py --verify <package>`) valida deterministicamente se os digests de cada fonte apontada no pacote correspondem exatamente aos bytes presentes na arvore.
- Se qualquer arquivo ou secao tiver digest divergente (drift): o pacote e rejeitado imediatamente (`status: stale_package_rejected`), impedindo tomada de decisao sobre premissas falsas e disparando a reconstrucao deterministica a partir das fontes oficiais.

### Consulta Mandatoria ao Advisor (Fase A)
Antes de congelar a spec, o Orquestrador invoca obrigatoriamente uma unica vez o papel **Advisor**, em sessao limpa, somente leitura (`report_only: true`), selecionado via Classifier MSC v3.
Challenge packet:
1. O protocolo proposto realmente reduz contexto ou apenas desloca custo?
2. Quais informacoes minimas sao necessarias para continuidade segura?
3. Como impedir que Short Resume Package vire fonte de autoridade?
4. Como detectar pacote stale, hash drift e revision drift?
5. Quando NAO devemos iniciar sessao nova?
6. Quais dados precisam ser reconstruidos diretamente das fontes oficiais?
7. Como impedir reintroducao de historico volumoso no bootstrap?
8. O protocolo deve ser automatico, recomendado ou condicionado por limiares mensuraveis?
9. Quais estados precisam sobreviver fora da conversa para retomada deterministica?

O parecer estruturado do Advisor (conforme `schemas/advisor-result.schema.json`) tera sua disposicao (`proceed`, `adjust`, `plan`, `debate`, `stop`) obrigatoriamente incorporada a spec antes do freeze.

### Acceptance Criteria Provisorios (Phase A)
- **AC01:** O compilador de contexto gera deterministicamente o Short Resume Package a partir do estado da arvore sem suposicoes ou campos nao auditaveis.
- **AC02:** O pacote curto cumpre estritamente `schemas/resume-manifest.schema.json` Draft 2020-12.
- **AC03:** O validador de integridade rejeita fail-closed qualquer pacote com hash divergente, fonte ausente ou seletor inexistente.
- **AC04:** Os contratos (`WORK_MODEL.md`, `orchestrator.md`, `orchestrator-playbook.md`) fixam expressamente que o pacote e indice, sem autoridade normativa propria.
- **AC05:** O playbook define as condicoes objetivas e limiares recomendados para transicao curta vs continuidade de sessao.
- **AC06:** Suporte cross-harness comprovado sem dependencia de estruturas proprietarias de sessao.
- **AC07:** Testes contrafactuais comprovam rejeicao de pacotes adulterados, deteccao de drift e recuperacao limpa.
- **AC08:** Zero vazamento de dados privados ou caminhos absolutos do host.
- **AC09:** `python3 scripts/validate_repository.py` aprovado sem desvios estruturais.
- **AC10:** Revisao final por Checker independente cross-family aprovada com zero action items.
