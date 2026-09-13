## 1. Avaliação formal do estado — Story 6.0a, rodada 1

**Veredito do Checker:** `changes_requested` (parecer `28ab4a9e-ee0f-4e3a-9e72-df1c2427e038`, Agy `gemini-3.1-pro-high`, família independente do Maker efetivo Codex `gpt-5.6-terra` — independência satisfeita conforme `checker_independence: preferred`).

O parecer contém 1 `action_item` (R1) e 2 itens `deferred`, `rejected` vazio. Em BMAD, `changes_requested` bloqueia o fechamento da story enquanto R1 não for tratado, independentemente da severidade rotulada (`medium`) do item individual — a rodada 1 permanece aberta.

## 2. Distinção R1 vs. observações não bloqueantes

| Item | Natureza | Bloqueia? | Fundamento |
| --- | --- | --- | --- |
| **R1** (`validateListenAddr`, `host=="" && port=="8080"`) | Defeito de comportamento | **Sim** | AC01 exige que "configuração atual Bling mantém comportamento"; o dev-report confirma, na própria seção "Escopo entregue", que a validação nova recusa `:8080` para "os dois listeners **existentes**" — isto é, a regra alcança o perfil Bling legado, não só o `mkauth-control-plane` novo. Regride comportamento aceito anteriormente para uma configuração explícita, contrariando AC01, sem que a spec (AC04) exija especificamente essa heurística de host/porta como critério de "default de produção". |
| Validação de material (KeyFile) ausente no perfil mkauth | `deferred`, severidade `low` | Não | O próprio Checker corretamente vincula à leitura de AC02 (handlers só ligados em 6.0b–d); a spec (§3 AC02) confirma essa fronteira. Não é lacuna desta fatia. |
| Falha em `internal/connectorgate` | `deferred`, severidade `low` | Não | Pré-existente, confirmada pelo dev-report ("nenhum arquivo daquele pacote foi alterado") e pela spec §5 (gate determinístico do conector é propriedade de C2.0b, "hoje ausente"). Fora do módulo desta story (spec §6: "uma story implementa somente seu módulo").

**Conferência do alvo do parecer contra spec/dev-report:** a localização `cmd/lynvia/internal/process/config.go: validateListenAddr` é consistente com o pacote (`cmd/lynvia/internal/process`) onde o dev-report registra as quatro alterações produtivas e a sonda M2/AC04 (`validateListenAddr`). Não há divergência de alvo — o achado está corretamente ancorado no código e no AC que motiva a validação (AC04) versus o AC que ela indevidamente atropela (AC01).

## 3. Encaminhamento proposto: **rework delimitado**

Não há base para contestação (o achado é concreto, evidenciado pelo próprio dev-report, e decorre de uma tensão real entre dois ACs da mesma spec — não de uma leitura equivocada do Checker) nem para impedimento (não há dependência externa ausente, gate humano pendente ou ambiguidade que trave a decisão; a correção é local e de baixo risco). Recomenda-se **rework delimitado ao achado R1**, sem reabrir os itens `deferred` nem tocar código fora do escopo já entregue pela story.

---

## 4. Briefing estruturado — Maker, rework R1 (Story 6.0a)

**Story:** `6-0a-configuracao-e-lifecycle-do-control-plane`
**Rodada:** rework R1 (pós-changes_requested da rodada 1)
**Escopo autorizado:** estritamente o achado R1. Não alterar `internal/connectorgate`, não introduzir validação de material (KeyFile) para o perfil `mkauth-control-plane`, não expandir para registry/ingress/bridge/fleet (6.0b–d).
**content_paths preservados:** apenas os arquivos já tocados pela entrega da rodada 1 em `cmd/lynvia/internal/process/` (incluindo `config.go` e os arquivos de teste correspondentes já listados no dev-report). Nenhum arquivo produtivo novo.

**Problema (R1):** em `cmd/lynvia/internal/process/config.go`, `validateListenAddr` usa a heurística `host == "" && port == "8080"` para recusar endereço, tratando-a como "default de produção". Essa regra é aplicada aos listeners existentes do perfil Bling, não apenas ao novo `mkauth-control-plane`, e portanto altera o comportamento aceito anteriormente para uma configuração explícita `:8080` — violando o requisito de AC01 de que "configuração atual Bling mantém comportamento".

**Ação exigida:** remover a regra arbitrária `host == "" && port == "8080"`. Manter a proteção contra endereço implícito/ausente apenas via:
- validação sintática com `net.SplitHostPort` (endereço malformado continua recusado);
- exigência de que o endereço tenha sido explicitamente configurado (endereço ausente continua recusado).

Não introduzir nenhuma outra heurística de "endereço default" não exigida literalmente por AC04. AC04 continua satisfeito por essas duas checagens (sintaxe + presença), sem reintroduzir o bloqueio de valores explícitos como `:8080`.

**Critérios de aceite envolvidos:**
- **AC01** — comportamento do perfil Bling legado deve permanecer inalterado para configurações explícitas de endereço, incluindo `:8080`.
- **AC04** — nenhum servidor deve iniciar implicitamente em endereço default; a prova continua exigida para endereço ausente/malformado, não para endereço explícito informado pelo operador.

**Verificação obrigatória antes de reportar:**
1. Restaurar as sondas contrafactuais já existentes (M1/AC01, M2/AC04) e confirmar que continuam vermelhas na mutação e verdes após restauração, com a nova versão de `validateListenAddr`.
2. Adicionar/ajustar caso de teste cobrindo explicitamente `:8080` (ou `0.0.0.0:8080` equivalente) como endereço aceito quando configurado explicitamente no perfil Bling — cenário que motivou o achado R1 — mapeando entrada/ação/esperado/observado no dev-report.
3. Repetir os comandos já documentados: `go test -v ./cmd/lynvia/internal/process/ -count=1`, `go build ./...`, `go vet ./...`, `git diff --check`.
4. Não é necessário reexecutar `make check` além de reconfirmar que o vermelho remanescente continua isolado em `internal/connectorgate` e inalterado por esta story (fora de escopo, já registrado como `deferred`).
5. Atualizar a tabela de ACs e a seção de sondas do dev-report apenas nos pontos afetados por R1; preservar o restante do relatório da rodada 1.

**Fora de escopo nesta rodada (não reabrir):** validação de material público/privado do perfil `mkauth-control-plane` (KeyFile) e o vermelho de `internal/connectorgate` — ambos permanecem como `deferred` de severidade `low`, conforme parecer do Checker e §5/§6 da spec.

---

Nenhuma alteração foi feita em disco e nenhum agente foi despachado; esta resposta é somente a proposta de condução e o briefing para o próximo passo, sujeitos a aprovação do usuário para o despacho efetivo do Maker.
