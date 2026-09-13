## 1. Avaliação formal do parecer (Checker, rodada 1)

O parecer é estruturalmente válido: `schema_version: 1`, `verdict: changes_requested`, um único `action_item` (R1, severidade `medium`, categoria `patch`, `target_role: maker`), dois itens em `deferred` (severidade `low`) e `rejected` vazio. O verdict `changes_requested` com `action_items` não-vazio bloqueia a aceitação da story — isso é o estado formal correto a reconhecer, não uma interpretação minha.

**R1** — único achado bloqueante:
- Local: `cmd/lynvia/internal/process/config.go: validateListenAddr`.
- Problema: a heurística `host == "" && port == "8080"` recusa `:8080` explícito como se fosse "endereço default de produção", mesmo quando essa configuração já era aceita no perfil Bling legado — o que contraria AC01 ("Configuração atual Bling mantém comportamento").
- Ação requerida: remover a regra arbitrária para `:8080`, preservando a proteção contra endereço implícito via `net.SplitHostPort` e exigência de configuração preexistente.

## 2. Distinção R1 × observações não bloqueantes

Os dois itens em `deferred` **não** integram o escopo do rework:
- KeyFile não validado no perfil `mkauth-control-plane` — o próprio Checker julga aceitável nesta fatia, pois handlers só chegam em 6.0b–d (AC02).
- Falha em `internal/connectorgate` — explicitamente marcada como preexistente e alheia ao diff desta story.

Nenhum dos dois deve entrar no briefing de rework; misturá-los ampliaria o escopo além do achado que efetivamente impede aceite.

## 3. Conferência do alvo contra spec e dev-report

- **AC01** citado pelo Checker corresponde literalmente à spec (§3, item 1): "Configuração atual Bling mantém comportamento."
- **AC04** citado corresponde à spec (§3, item 4): "Nenhum servidor é iniciado implicitamente em endereço default de produção" — mas a spec fala em endereço *implícito*, não em recusar um valor *explicitamente configurado*. É essa distinção que sustenta o achado.
- O local apontado (`validateListenAddr`) e a evidência citada (`0.0.0.0:8080` aceito vs. `:8080` recusado com a mensagem "endereço webhookd usa default de produção") batem com o próprio dev-report: a linha de verificação do AC04 usa exatamente `WebhookListenAddr=:8080` como entrada e reporta esse retorno como resultado *esperado e observado*, e a sonda contrafactual M2 confirma que essa mesma checagem é a que torna `TestNewFromConfigRejectsProductionDefaultAddressBeforeOpeningDatabase` vermelho quando removida.
- Ou seja: o Maker tratou `:8080` como sinônimo de "default de produção" e validou essa interpretação como sucesso do AC04 — sem testar o caso legado de `:8080` explicitamente configurado no perfil Bling sob AC01. O dev-report não contém nenhuma linha que refute a alegação do Checker (não há teste de regressão que exercite `:8080` no perfil Bling legado). O achado é, portanto, consistente com a lacuna de evidência do próprio relatório, não uma invenção do Checker.

Código-fonte não está disponível nesta rodada (`code_tree: not_observable`), então a conferência aqui se limita à consistência documental — que se sustenta.

## 4. Encaminhamento proposto

**Rework delimitado ao achado R1**, não contestação e não impedimento:

- Não cabe **contestação**: não há, no recorte documental, nenhuma evidência que desminta o achado — pelo contrário, a lacuna de teste de regressão para `:8080`/Bling legado é real e visível no próprio dev-report.
- Não cabe **impedimento**: o achado tem local, causa e ação corretiva precisos (`validateListenAddr`), sem dependência externa, gate humano (G3/G5) ou decisão de ratificação pendente. É uma correção de patch autocontida no arquivo já tocado pela story.
- Cabe **rework delimitado**: escopo estrito a `validateListenAddr` (e, por regressão, aos testes já existentes — `TestNewFromConfigBlingProfileRequiresBlingConnection`, `TestNewFromConfigRejectsProductionDefaultAddressBeforeOpeningDatabase`, mais um caso novo cobrindo `:8080` explícito no perfil Bling legado). Os demais `content_paths` já entregues (declaração de `Config.Profile`, `Compose`/`Set`/`validateSufficient`, slot lifecycle `mkauth-control-plane`) permanecem intocados — não fazem parte do achado e alterá-los extrapolaria o mandato do rework.

## 5. Briefing estruturado — Maker, rework R1

```
story_id: 6-0a-configuracao-e-lifecycle-do-control-plane
phase: rework
round: R1
spec_revision: story-6.0a-r1
verdict_origem: changes_requested (checker-6-0a-r1.md)

escopo_autorizado:
  - arquivo: cmd/lynvia/internal/process/config.go
  - função: validateListenAddr
  - proibido: qualquer alteração fora deste arquivo/função; não tocar
    Config.Profile, Compose, Set, validateSufficient nem o slot lifecycle
    mkauth-control-plane (fora do escopo de R1, entregues e aprovados).

achado_a_corrigir (R1):
  problema: >
    A heurística `host == "" && port == "8080"` recusa `:8080` explícito
    como "endereço default de produção", alterando o comportamento do
    perfil Bling legado (viola AC01: "Configuração atual Bling mantém
    comportamento").
  ação_requerida: >
    Remover a regra que recusa especificamente `host == "" && port ==
    "8080"`. Preservar a proteção do AC04 (nenhum servidor sobe em
    endereço default *implícito*) apenas via:
      (a) validação sintática do endereço com net.SplitHostPort, e
      (b) exigência de que o endereço tenha sido explicitamente
          configurado (não herdado de valor zero/ausente).
    Não reintroduzir bloqueio a valores explicitamente fornecidos pelo
    operador, incluindo `:8080` quando presente na configuração Bling.

não_incluir_neste_rework (deferred, não bloqueante):
  - Validação de KeyFile ausente no perfil mkauth-control-plane
    (aceito pelo Checker como fora desta fatia; tratar em 6.0b–d).
  - Falha preexistente em internal/connectorgate
    (alheia ao diff da story; não mexer).

verificação_exigida:
  - Reexecutar TestNewFromConfigBlingProfileRequiresBlingConnection e
    TestNewFromConfigRejectsProductionDefaultAddressBeforeOpeningDatabase;
    ambos devem permanecer verdes.
  - Adicionar (ou ajustar) teste de regressão cobrindo `:8080` explícito
    no perfil Bling legado, demonstrando que a configuração é aceita
    normalmente (não mais recusada como "default de produção").
  - Manter a sonda contrafactual M2 (remoção de validateListenAddr)
    como prova de que a proteção ao endereço implícito continua ativa
    após a correção.
  - Repetir go build ./... e go vet ./... do módulo lynvia; não é
    necessário reabrir o vermelho preexistente de internal/connectorgate
    (fora de escopo, já registrado nos limites do dev-report).
  - Preservar fixtures sintéticas e ausência de rede externa/efeito de
    laboratório (G5 continua fora de escopo desta story).

entregável_esperado:
  - Diff mínimo restrito a validateListenAddr e seus testes diretos.
  - Dev-report R1 atualizado: nova linha de evidência para AC01 cobrindo
    `:8080` no perfil Bling; linha de AC04 revisada para deixar explícito
    que a proteção remanescente é contra endereço implícito/ausente, não
    contra valor explícito reconhecido.

fora_de_escopo (explícito):
  - Qualquer mudança em registry, ingress, bridge, fleet ou material de
    chave pública/privada (pertence a 6.0b–d, conforme dev-report).
  - Qualquer alteração em internal/connectorgate.
```

**Nota de encerramento (modo somente leitura):** nenhum arquivo foi alterado e nenhum agente foi despachado nesta sessão; o texto acima é a proposta de condução e o briefing a ser usado, se autorizado, no próximo despacho efetivo ao Maker.
