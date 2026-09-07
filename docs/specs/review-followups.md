# Revisão posterior por outra família e registro `Agent runs`

Revisão: 1 (congelada em 2026-09-07, parecer favorável do maintainer). Implementação: não autorizada. Publicação: não autorizada.
Alteração de política de consumidores (`checker_independence`): fora deste contrato.

## 1. Objetivo

Trabalhar com a família disponível, concluir Tasks sob uma política autorizada e receber, em
ativações futuras, a sugestão de revisão por outra família, sem esperar renovação de quota e sem
flexibilizar silenciosamente uma exigência `required`.

## 2. O que já existe (sem mudança)

- `checker_independence: preferred`: fallback para mesma família em sessão nova, só com
  indisponibilidade comprovada, registrando `same_family_fresh_session`
  (`prompts/orchestrator-perfis.md#independência-do-checker`).
- `required` bloqueia; política local estrita vigente até mudança autorizada.
- Critérios de aceite e achados necessários seguem impedindo aprovação (contrato do Checker).
- Parecer vinculado a `content_id`; reuso proibido após alteração material
  (`docs/WORK_MODEL.md#conclusão`, `#registro-de-revisão`).
- Prova de indisponibilidade: quota esgotada, autenticação recusada ou harness ausente comprovam;
  timeout isolado, saída vazia ou processo vivo não (`#fallback-e-interrupção`).
- Evidência de story BMAD registrada no artefato próprio da story (playbook, Fechamento).

## 3. Identidade de unidade

Reutiliza a identidade do contrato existente (`active_work_ref`):
`<method>/<unit_type>/<id | area_id:id>@<source_location>`.

- Native sem módulos: `native/task/T003@_tl-orc/project/tasks/T003-slug.md`.
- Native multiárea: `native/task/billing:T003@modules/billing/_tl-orc/project/tasks/T003-slug.md`.
- BMAD sem módulos: `bmad/story/1.1@_bmad-output/implementation-artifacts/sprint-status.yaml`.
- BMAD multiárea: `bmad/story/billing:1.1@modules/billing/_bmad-output/.../sprint-status.yaml`.

A mesma identidade aparece no alvo da pendência, no follow-up, na tabela `Agent runs` e no
registro de revisão. Duas stories com o mesmo ID em áreas diferentes são unidades distintas.

## 4. Fonte oficial da pendência

A pendência nasce na rodada de revisão que a gera e mora somente ali:

- Native: bloco `## Review follow-up` em `project/evidence/<Tnnn>-rNN.md` da área da unidade.
- BMAD: o mesmo bloco no artefato de evidência próprio da story, na área da story.

Task, STATUS e registros BMAD apenas referenciam (caminho e âncora). Nenhuma Task Native é
criada para acompanhar uma story. Atualizações de acompanhamento são registros de controle:
acrescentam entradas datadas ao bloco, não modificam o alvo nem o parecer original.

```text
## Review follow-up
id: RF-<unit_id>-rNN
target:
  unit: <identidade §3>
  spec_revision: <s>
  content_id: <formato vigente de WORK_MODEL.md#versão-do-trabalho: com Git, commit base mais hash do conjunto de alterações; sem código, hashes dos artefatos listados>
  content_paths: [...]
  locator: <commit | artefato preservado | not_recoverable>
origin_review: <rNN> run_id: <run_id do Checker de mesma família>
limitation: same_family_fresh_session
families_used: [<Maker, reworks, correção própria do Orquestrador, Checker>]
status: pending | superseded | closed
review_ref: <evidence#rNN run_id=...> | none
attempts: [<rNN run_id=... verdict=...>]
superseded_by: <RF-...> | none
supersedes: <RF-...> | none
reason: <texto obrigatório em superseded e em not_recoverable>
log:
  - <UTC> <evento>
```

## 5. Estados e fechamento

- `pending`: alvo registrado aguarda parecer independente.
- `closed`: somente com parecer `approved`, em sessão nova, de família distinta de todas as
  `families_used`, cujo registro cubra exatamente o alvo (unidade, `spec_revision`, `content_id`).
  `review_ref` guarda evidência, rodada e `run_id`. Aprovação em outra unidade ou outro
  `content_id` não transporta.
- `changes_requested`: mantém `pending`, acrescenta a rodada em `attempts`.
- `superseded`: exige `superseded_by` apontando para uma pendência substituta sobre o conteúdo
  novo e `reason` que explique quais garantias do alvo original continuam cobertas pelo novo alvo
  e quais foram alteradas ou retiradas, citando a decisão registrada. Dois `content_id` não bastam.
  A substituta registra sua procedência em `supersedes` e nasce `pending`, quando ainda falta a
  revisão independente, ou `closed`, quando já existe parecer independente `approved` cobrindo
  exatamente o novo alvo. A pendência original nunca é fechada pelo parecer do conteúdo novo, e a
  substituta não inventa uma nova revisão de mesma família: seu `origin_review` é o da original.
- Alteração posterior do conteúdo não fecha nem apaga a pendência. Se o alvo não puder ser
  recuperado (`locator: not_recoverable`), a pendência permanece `pending` com essa limitação e a
  revisão posterior declara o que examinou.
- `done` continua permitido sob `preferred` com pendência aberta; Deliverable lista pendências
  abertas ao fechar sem bloquear. Sob `required`, ausência de família distinta bloqueia. A
  indisponibilidade nunca converte `required` em `preferred`.

## 6. Revisão posterior e autorização

A revisão posterior é rodada nova `rNN`, sessão nova, outra família, sobre o alvo registrado
quando recuperável, ou sobre o conteúdo atual com pendência substituta quando houver decisão
registrada de substituição. Ela não autoriza corrigir uma Task concluída:

- com autorização vigente que cubra o retrabalho, segue o fluxo normal: nova rodada, novo
  `content_id` e pendência substituta vinculada (§5), `pending` ou `closed` conforme o parecer
  obtido sobre o novo alvo;
- sem autorização, a pendência é preservada com o parecer em `attempts` e os achados entram na
  fila apropriada (Task `fix`/`analysis` em `draft` na área responsável, ou referência à unidade
  BMAD existente), sem despachar implementação.

Resultado histórico da Task, revisão posterior e autorização para novas alterações ficam separados.

## 7. STATUS e ativação

- Cabeçalho global de STATUS ganha `review_followups: [<unit>@<evidence_ref>#RF-id]`, derivado e
  reconstruível a partir das evidências; presente em `native` e `bmad`.
- Na ativação, com lista não vazia e candidatos elegíveis de outra família no catálogo, o menu
  oferece "Revisar por outra família (n)". A oferta afirma elegibilidade, não disponibilidade.
  Apresentar o menu não autoriza chamadas pagas nem escrita de registros; a ativação somente
  leitura apenas lê e informa. Sem daemon e sem detecção de renovação de quota.

## 8. Disponibilidade

Aparecer no catálogo prova apenas elegibilidade. A disponibilidade se comprova por evidência
recente pertinente (run registrado no mesmo harness, mesma conta, mesma sessão de trabalho) ou
pela própria chamada autorizada ao papel. Sonda separada só quando resolver uma dúvida concreta
(estado `unknown` após a chamada normal). Falha da chamada normal com erro que comprove
indisponibilidade aciona o fallback; timeout isolado e saída vazia não. Toda chamada, inclusive a
que falhou, entra em `Agent runs`.

## 9. `Agent runs`

Tabela uniforme no Evidence round e, opcionalmente, na Discussion:

| run_id | role | harness | model | effort | family | session | phase | round | outcome | fallback_reason |

A tabela herda a identidade completa `unit` (§3) do cabeçalho da evidência em que está; não
há coluna própria de unidade.

- `run_id` = `<unit_id>-rNN-<role>-<seq>`, único na evidência da unidade; `unit_id` é o `id`
  qualificado da identidade (§3), sem caminho.
- O registro de revisão cita o `run_id` do Checker junto de `content_id`, `spec_revision` e
  limitação. O parecer JSON não muda de schema.
- Tentativas descartadas, chamadas falhas e sondas entram como linhas com `outcome` e motivo.
  Dado não observável é escrito `not_observable`, nunca omitido nem inferido.

## 10. Arquivos afetados

`prompts/orchestrator-perfis.md` (independência: famílias efetivas incluindo reworks e correção
própria; pendência sob `preferred`; disponibilidade §8), `docs/WORK_MODEL.md` (identidade §3,
conclusão, registro de revisão, bloco §4, `review_followups`, templates), `prompts/orchestrator-playbook.md`
(preparar, fechamento, §6), `SKILL.md` (item de menu, §7), `docs/PROJECT_CONFIGURATION.md` (uma
frase), `CHANGELOG.md`. Schemas e manifesto inalterados. Release menor.

## 11. Verificação

Teste de estrutura (consumidor sintético, falhas controladas, sem harness pago):

1. Mesma família com prova controlada de indisponibilidade sob `preferred`: bloco criado na
   evidência, `done` permitido, STATUS referencia por caminho.
2. Mesma situação sob `required`: bloqueio com ponto de retomada; sem bloco; sem flexibilização.
3. Ativação somente leitura com pendência e outra família no catálogo: menu oferece; nenhuma
   chamada e nenhuma escrita ocorrem.
4. Parecer `approved` de outra família cobrindo o alvo: `closed` com `review_ref` e `run_id`.
5. `changes_requested` sem autorização vigente: `pending`, `attempts` atualizado, achados na fila
   como `draft`, nenhuma implementação despachada.
6. `changes_requested` com autorização vigente: retrabalho, novo `content_id`, substituta vinculada
   com `supersedes` e `reason` de escopo. Variante 6b: o retrabalho já recebe parecer independente
   `approved` sobre o novo alvo; a substituta nasce `closed` com `review_ref`, a original fica
   `superseded`, nenhuma pendência permanece aberta e nenhuma revisão de mesma família é inventada.
7. Conteúdo alterado sem revisão: pendência original `pending`; nova revisão de mesma família no
   conteúdo novo cria substituta com `reason` de escopo; ausência de `reason` é rejeitada.
8. `approved` de outra família com `content_id` diferente do alvo: não fecha.
9. Mesmo `content_id` em outra unidade: não transporta.
10. Duas stories BMAD `1.1` em `billing` e `identity`: pendências distintas, blocos nos artefatos
    de cada área, nenhuma Task Native, STATUS global lista as duas identidades completas.
11. Projeto sem módulos com story BMAD: identidade sem `area_id`, mesmo fluxo.
12. Alvo não recuperável (commit ausente, artefato apagado): `pending` com limitação registrada.
13. Falha controlada de timeout: sem fallback para mesma família; falha controlada com erro de
    quota: fallback; ausência de identificador de sessão: `not_observable`.
14. Tentativas descartadas do Classificador preservadas em `Agent runs`.
15. Orquestrador que corrigiu por conta própria: sua família em `families_used`.

Teste de comportamento (harness real, somente para o que a estrutura não prova; os itens 16–18
podem compartilhar uma mesma execução real quando ela produzir as evidências necessárias):

16. Chamada normal ao Checker comprova disponibilidade sem sonda separada e gera a linha de run.
17. O Checker de família distinta lê o alvo pelo `locator` e devolve exclusivamente o parecer JSON
    conforme o schema, sem escrever arquivos nem acrescentar metadados. O Orquestrador preserva o
    parecer íntegro e registra sua associação com `run_id`, `content_id` e `spec_revision` no
    registro de revisão; a verificação confere a leitura do alvo e essa associação.
18. Checker de família distinta valida a redação nova (AC de texto normativo único, sem contradição
    com reclassificação por fase e independência).
