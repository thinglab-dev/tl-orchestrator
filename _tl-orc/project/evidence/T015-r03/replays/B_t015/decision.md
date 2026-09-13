Tenho todo o recorte necessário (spec §3, dev-report escopo entregue, parecer do Checker r1, PROJECT.md frontmatter) e a árvore de código está confirmada `not_observable` — a decisão abaixo é baseada estritamente nesses documentos, sem inspeção de código real.

## 1. Avaliação formal do estado — Story 6.0a, rodada 1

**Veredito do Checker:** `changes_requested`, com **1 action item bloqueante (R1, severity medium, category patch)** e 2 itens `deferred` (não bloqueantes, ambos `low`), `rejected: []`.

| Achado | Natureza | Bloqueia merge? |
|---|---|---|
| R1 — heurística `host=="" && port=="8080"` em `validateListenAddr` | Divergência de comportamento vs. contrato | **Sim** |
| Deferred 1 — validação de KeyFile ausente no perfil mkauth | Fora do escopo desta fatia (handlers só chegam em 6.0b–d) | Não |
| Deferred 2 — falha preexistente em `internal/connectorgate` | Externo ao escopo modificado pela story | Não |

## 2. Distinção do achado R1 e verificação cruzada contra spec/dev-report

**O que o dev-report declara ter entregue** (`## Escopo entregue`): "endereço ausente, malformado ou `:8080` é recusado" — confirma que o Maker implementou exatamente a regra que o Checker está apontando como defeituosa. Não há divergência de leitura entre Checker e dev-report quanto ao fato; a divergência é sobre se esse comportamento é *correto*.

**Confronto contra a spec (§3):**
- **AC01** exige que "Configuração atual Bling mantém comportamento" — um perfil legado que já usa `:8080` explicitamente na configuração deixa de funcionar com a regra atual, o que é uma quebra direta de AC01.
- **AC04** exige apenas que "Nenhum servidor é iniciado implicitamente em endereço default de produção" — a proibição é sobre inicialização *implícita*, não sobre a string literal `:8080` quando ela vem de configuração explícita e pré-existente. A regra do Maker generalizou incorretamente "não usar default implícito" para "recusar a porta 8080 mesmo quando declarada", o que não está no texto do AC04.

**Conclusão da verificação:** o achado R1 é procedente e corretamente qualificado como bloqueante — ele aponta uma violação real de AC01 (regressão comportamental do perfil Bling) causada por uma leitura excessivamente literal/heurística de AC04. Não é uma observação estética nem um gold-plating do Checker; é um defeito de aceite. Os dois itens `deferred` estão corretamente classificados como não bloqueantes (um é escopo de story futura 6.0b–d por design do próprio AC02; o outro é falha preexistente fora do diff desta story) e não devem ser puxados para este rework.

## 3. Encaminhamento proposto

**Rework delimitado ao achado R1**, sem contestação — não há base documental para impedimento (o achado é acionável e a solução é descrita no próprio `required_action` do Checker) nem para contestar o veredito (a leitura do Checker é mais aderente ao texto literal de AC01/AC04 do que a implementação atual).

Autorização vigente: `PROJECT.md` (frontmatter) declara `work_method: bmad`, `routing_mode: classifier` — não há indicação de política que amplie escopo de rework além do achado aberto; portanto o rework deve permanecer estritamente confinado a R1, preservando os dois itens `deferred` como pendências registradas e não como tarefas desta rodada.

**Classificação do achado (conforme lição operacional registrada):** `fix` — divergência de contrato (comportamento diverge do AC01 declarado), não `analysis` nem limitação de ambiente.

---

## Briefing estruturado — Maker rework R1 (Story 6.0a)

```yaml
unit: bmad/story/6.0a
phase: rework
round: R1
spec_revision: story-6.0a-r1
finding_id: R1
finding_severity: medium
finding_category: fix
verdict_origin: changes_requested (checker-6-0a-r1.md)

scope:
  in_scope:
    - "Remover exclusivamente a regra heurística `host == \"\" && port == \"8080\"` em
       validateListenAddr que rejeita a configuração explícita `:8080` do perfil
       legado Bling."
  out_of_scope:
    - "Validação de KeyFile/material público-privado ausente no perfil
       mkauth-control-plane (deferred, low, fora desta fatia — handlers só
       são ligados em 6.0b–d, conforme AC02)."
    - "Falha preexistente em internal/connectorgate (deferred, low, externa
       ao diff desta story — não tocar)."
  content_paths_preserved:
    - "cmd/lynvia/internal/process/config.go: validateListenAddr"
    - "cmd/lynvia/internal/process/config.go: normalizeConfig"
    # Nenhum arquivo/função além dos citados pelo parecer do Checker deve
    # ser tocado nesta rodada.

required_action: >
  Remover a regra arbitrária que recusa host == "" && port == "8080", de
  modo a preservar o comportamento do perfil Bling (AC01). Manter a
  proteção contra endereços implícitos exigida por AC04 exclusivamente
  através de: (a) validação sintática com net.SplitHostPort, e (b)
  exigência de que o endereço já exista em configuração preexistente
  (isto é, não seja preenchido por default de produção quando ausente).

acceptance_gate:
  - "AC01: uma configuração de perfil Bling que declara `:8080` explicitamente
     é aceita e produz o comportamento atual (não regride as cinco
     instalações legadas)."
  - "AC04: um endereço ausente/omitido continua sendo recusado (nenhum
     servidor sobe implicitamente em default de produção); apenas a
     ausência/malformação é rejeitada, não o valor \"8080\" per se quando
     explicitamente configurado."
  - "AC02/AC03 permanecem intactos — não alterar lifecycle do slot
     mkauth-control-plane nem o caminho de teste via NewFromConfig."

do_not:
  - "Não introduzir nova semântica para distinguir 'checagem por profile'
     além do que os quatro ACs já exigem."
  - "Não expandir o rework aos dois itens deferred (documentar que
     permanecem pendentes, não resolvê-los aqui)."
  - "Não tocar internal/connectorgate (falha preexistente, fora do escopo
     do diff desta story)."

next_review:
  target_role: checker
  independence: manter família independente da rodada 1 (conforme registrado
    em PROJECT.md / lições operacionais — não reutilizar o mesmo autor do R1).
  must_confirm:
    - "AC01 e AC04 ambos satisfeitos simultaneamente pela nova validação."
    - "Nenhuma mudança fora de validateListenAddr/normalizeConfig conforme
       delimitado."
    - "Os dois itens deferred permanecem registrados como pendências, não
       silenciosamente descartados nem resolvidos fora de escopo."

provenance_note: >
  Árvore de código da rodada 1 marcada not_observable (congelamento T015).
  Este briefing é construído estritamente sobre o recorte documental:
  spec-6-0a.md §3, dev-report-6-0a.md (Escopo entregue) e checker-6-0a-r1.md
  (Parecer). Qualquer alocação de arquivo/função fora das citadas pelo
  próprio parecer do Checker exige nova verificação documental antes de
  autorização.
```

**Resumo:** R1 é bloqueante e procedente (regressão de AC01 por heurística não prevista no contrato); os 2 itens `deferred` ficam registrados, fora deste rework. Encaminhamento: rework delimitado, sem contestação, sem impedimento. Nenhum arquivo foi modificado e nenhum agente foi despachado — esta resposta é a proposta e o briefing solicitados.
