## 1. Estado formal da Story 6.0a

Parecer do Checker (rodada 1): `verdict: changes_requested`, com **um único `action_item` bloqueante (R1, severity medium, target_role: maker)** e **dois itens em `deferred` (severity low)**. Conforme o contrato do Checker report-only, `deferred` não bloqueia critério de aceite — são observações registradas para ciência, não condição de aprovação. Portanto, formalmente, **apenas R1 impede o fechamento da rodada 1**.

Os dois itens deferidos (validação de material mkauth ausente; falha preexistente em `internal/connectorgate`) estão corretamente classificados como não bloqueantes pelo próprio Checker, com justificativa plausível (AC02 posterga handlers para 6.0b–d; falha é externa ao diff). Não há disputa a levantar sobre eles nesta rodada.

## 2. Confronto do achado R1 contra spec e dev-report — achado é contestável

Reconstruí o alvo citado por R1 (`validateListenAddr`, rejeição de `host=="" && port=="8080"`) contra as duas fontes congeladas que o próprio Checker deveria ter usado:

- **Spec, AC04 (§3, linha 23):** *"Nenhum servidor é iniciado implicitamente em endereço default de produção; validar endereços ... por função."*
- **Dev-report, tabela de ACs, linha AC04:** entrada de teste é **exatamente** `WebhookListenAddr=:8080` (Bling), esperado = *recusar configuração antes de bootstrap/listener*, observado = recusado com "endereço webhookd usa default de produção", sem abrir banco. **Esse é o cenário de aceite já ratificado na spec**, não uma invenção do Maker.
- **Dev-report, sonda M2:** remover as chamadas a `validateListenAddr` tornou vermelho exatamente `TestNewFromConfigRejectsProductionDefaultAddressBeforeOpeningDatabase` — ou seja, a validação que R1 pede para remover é a que a própria sonda contrafactual da story comprova como necessária para AC04.

O `required_action` de R1 — "remover a regra que recusa `host=="" && port=="8080"`" — **implementado literalmente, reverteria um AC já ratificado na spec congelada (AC04) e regrediria a sonda M2 de vermelho→verde para verde→vermelho**. Não há, nas fontes entregues, nenhuma leitura de AC01 que seja violada por essa validação: a sonda M1 e os cinco testes de wiring do perfil Bling legado permanecem verdes com a regra presente; R1 não aponta qual teste de regressão Bling quebrou, apenas infere risco ("afeta quem já configurava `:8080`") sem evidência de um caso concreto coberto por AC01.

Agravante relevante: a própria ficha de classificação de `review — rodada 1`, anexada ao mesmo parecer, admite em `uncertainties`: *"O briefing não contém o diff, a spec AC01–AC04 nem o relatório completos para inspeção direta."* Ou seja, o Checker que emitiu R1 registra formalmente que operou **sem acesso ao texto integral de AC04 e ao dev-report** — exatamente as duas fontes que, quando conferidas agora, contradizem o achado.

**Nota de procedência menor:** `resume.json` aponta o seletor `frontmatter` para `PROJECT.md`, mas o arquivo lido não contém bloco `---` de frontmatter (começa direto em `format_version: 1`). Não afeta o mérito de R1, mas é uma discrepância de citação que vale registrar para a trilha de evidência.

## 3. Encaminhamento proposto

Dentro da autorização vigente (somente leitura, sem despacho efetivo), o encaminhamento cabível **não é rework cego de R1**. Executar o `required_action` como escrito causaria regressão documentada contra um AC ratificado. O encaminhamento correto é:

**Contestação fundamentada de R1**, dirigida à próxima rodada de revisão (Checker/Debater), com citação direta de AC04, da linha AC04 do dev-report e da sonda M2 — sem reabrir os itens `deferred`, que permanecem aceitos como estão. Isto não é um impedimento (não há ambiguidade documental insuperável: as fontes congeladas bastam para decidir) nem um rework de código (não há defeito real a corrigir no comportamento descrito). É a terceira via prevista na tarefa.

Isto é rodada 1 de rework (ainda distante do limiar de escalonamento consultivo N=3), então a via normal é devolver o achado com evidência, não escalar.

---

## 4. Briefing estruturado — próxima fase (resposta a R1, rodada 1)

> Emitido apenas como proposta nesta sessão somente leitura; nenhum agente foi despachado.

```yaml
schema_version: 1
story_id: 6-0a-configuracao-e-lifecycle-do-control-plane
phase: rework_response
round: 1
target_finding: R1
scope: >
  Estritamente o achado R1 do parecer checker-6-0a-r1.md. Não reabrir os itens
  `deferred` (validação de material mkauth; falha preexistente em
  internal/connectorgate), que permanecem aceitos como registrados.
content_paths_preserved:
  - cmd/lynvia/internal/process/config.go: validateListenAddr
posicao: contestacao_fundamentada
razao:
  - "AC04 (spec-6-0a.md §3, linha 23) exige recusar início de servidor em
     endereço default de produção; o cenário de teste do próprio AC04 no
     dev-report usa WebhookListenAddr=:8080 no perfil Bling como a entrada
     que deve ser recusada — este é o comportamento já ratificado, não uma
     invenção do Maker."
  - "A sonda contrafactual M2 (dev-report-6-0a.md, tabela de sondas) demonstra
     que remover as chamadas a validateListenAddr torna vermelho
     TestNewFromConfigRejectsProductionDefaultAddressBeforeOpeningDatabase.
     O required_action de R1 pede exatamente essa remoção, o que reverteria
     uma prova de regressão já estabelecida para AC04."
  - "R1 não cita nenhum teste de wiring do perfil Bling legado (AC01) que
     tenha quebrado; a sonda M1 e os cinco testes de wiring legado permanecem
     verdes com a validação presente."
  - "O próprio registro de classificação anexo ao parecer (fase review,
     rodada 1) declara em uncertainties que o briefing do Checker não
     continha o diff, a spec AC01–AC04 nem o dev-report completos para
     inspeção direta — o que é consistente com a leitura equivocada de AC04
     identificada acima."
acao_solicitada_ao_checker:
  - "Reconsiderar R1 à luz do texto integral de AC04 e da linha AC04/sonda M2
     do dev-report, ambos agora citados nesta resposta."
  - "Indicar, se a discordância persistir, qual caso concreto de configuração
     Bling legada (coberto por AC01) seria indevidamente recusado pela regra
     atual — na ausência desse caso concreto, recomenda-se retirar R1 e
     emitir verdict approved, mantendo os dois itens deferred como estão."
nao_incluido_neste_briefing:
  - "Qualquer alteração de código em validateListenAddr."
  - "Reabertura dos itens deferred (severity low)."
limite_de_autorizacao: >
  Este briefing é uma proposta de conduta e resposta fundamentada; nenhum
  despacho de Maker, Checker ou Debater foi realizado nesta sessão, e nenhum
  arquivo em disco foi modificado.
```

**Resumo da posição:** R1 é o único achado bloqueante da rodada 1, mas contradiz AC04 e a sonda M2 já presentes nas fontes congeladas; a evidência aponta para contestação fundamentada — não para rework literal do `required_action` — como o encaminhamento correto dentro da autorização vigente.
