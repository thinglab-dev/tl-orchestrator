## Avaliação formal — Story 6.0a, rodada 1

**Verdict do Checker:** `changes_requested`, com 1 action item bloqueante (R1) e 2 itens `deferred` (não bloqueantes).

### Achado R1 — bloqueante, confirmado contra spec e dev-report

- **Target:** `cmd/lynvia/internal/process/config.go: validateListenAddr`
- **Problema:** a validação recusa `host == "" && port == "8080"` (ou seja, `:8080`), tratando esse endereço explícito como se fosse default implícito de produção.
- **Confronto com AC01** ("Configuração atual Bling mantém comportamento"): o dev-report confirma textualmente que a regra foi implementada como descrita pelo Checker — *"endereço ausente, malformado ou `:8080` é recusado"*. Isso é uma mudança de comportamento em relação ao perfil legado Bling, que pode ter `:8080` configurado explicitamente. AC01 é violado.
- **Confronto com AC04** ("Nenhum servidor é iniciado implicitamente em endereço default de produção"): AC04 protege contra inicialização *implícita*, não proíbe configuração explícita de `:8080`. A heurística do Maker excede o critério, criando uma semântica não pedida pela spec.
- **Classificação:** defeito real, não é opinião de estilo — impede o critério de aceite obrigatório AC01. Confirma-se o `severity: medium` / `category: patch` do Checker.

### Itens deferred — corretamente não bloqueantes

1. **Validação de material público/privado ausente no perfil mkauth** — o próprio Checker reconhece que os handlers só serão ligados em 6.0b–d (AC02), então a ausência de validação de `KeyFile` nesta fatia é aceitável. Não há conflito com AC04, que exige validação "por função" — a função ainda não existe nesta story.
2. **Falha preexistente em `internal/connectorgate`** — alheia ao escopo modificado pela story; oráculo de teste desatualizado, não uma regressão introduzida por 6.0a.

Ambos estão corretamente fora do escopo de rework obrigatório e não devem ser incluídos no briefing de R1.

## Encaminhamento proposto

**Rework delimitado ao achado R1.** Não há base para contestação (o próprio dev-report confirma o comportamento apontado pelo Checker, e a violação de AC01 é objetiva) nem motivo de impedimento (o fix é local e de baixo risco, dentro da autorização vigente da story). Os itens `deferred` permanecem registrados para tratamento futuro (mkauth material validation entra naturalmente em 6.0b–d; connectorgate é problema de outro escopo) e **não** entram neste rework.

---

## Briefing — Maker, rework R1 (Story 6.0a)

```
schema_version: 1
work_ref: bmad/story/6.0a@_tl-orc/project/evidence/T015-r01/inputs/checkpoint-B/spec-6-0a.md
phase: rework
target_round: r1-rework
scope: strictly_R1
```

**Objetivo único:** remover a regra heurística que recusa `host == "" && port == "8080"` em `validateListenAddr`, preservando toda a proteção restante contra endereços implícitos.

**Localização:** `cmd/lynvia/internal/process/config.go`, função `validateListenAddr` (chamada a partir de `normalizeConfig`, mesmo arquivo). **Não tocar em outras funções ou arquivos** — o rework é estritamente cirúrgico.

**Ação requerida (conforme `required_action` do Checker):**
- Eliminar a checagem arbitrária `host == "" && port == "8080"`.
- Manter a validação sintática via `net.SplitHostPort` (endereço malformado continua recusado).
- Manter a exigência de configuração preexistente (endereço ausente continua recusado) — isso já satisfaz AC04 sem precisar de heurística de porta.

**Critério de aceite a restaurar:** AC01 — a configuração atual do perfil Bling (incluindo `:8080` explícito) deve continuar funcionando sem alteração de comportamento.

**Fora de escopo neste rework** (não fazer):
- Validação de material público/privado (KeyFile) do perfil `mkauth-control-plane` — item deferred, tratado nas stories 6.0b–d.
- Qualquer ação sobre a falha em `internal/connectorgate` — problema preexistente, fora do escopo da story.
- Qualquer refatoração adicional em `normalizeConfig`, `Compose`, `Set` ou `validateSufficient` além do necessário para remover a regra de `:8080`.

**Content paths a preservar (não modificar):**
- Toda a lógica de perfis (`Config.Profile`, default `bling`, composição `mkauth-control-plane` sem Bling/Lytex/webhook/opsview).
- Lifecycle do slot `mkauth-control-plane` (`Run`/`Shutdown`/`InFlight`) sem listener/handler — inalterado por esta story (reservado a 6.0b–d).
- Obrigatoriedade de material do webhook apenas quando a superfície Bling está declarada.

**Definição de pronto para o rework:**
- `:8080` explícito volta a ser aceito quando configurado.
- Endereço ausente e endereço malformado continuam recusados (regressão zero nas demais proteções de AC04).
- AC01 e AC04 validados juntos; nenhuma alteração fora de `validateListenAddr`/`normalizeConfig` no arquivo indicado.

---

Nada foi modificado em disco nem nenhum agente foi despachado — esta resposta é apenas a proposta de condução e o briefing estruturado, conforme o modo somente leitura solicitado.
