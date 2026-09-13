Tenho evidência suficiente e verificada por digest. Segue a proposta formal.

---

## 1. Avaliação do estado da Story 6.0a

**Verdict do Checker (r1): `changes_requested`**, com 1 action item (R1, severidade *medium*), 2 itens em `deferred` (baixa severidade, fora de escopo) e nenhum item em `rejected`.

O achado **R1** aponta um defeito concreto:

- **Local:** `cmd/lynvia/internal/process/config.go: validateListenAddr`
- **Problema:** a heurística `host == "" && port == "8080"` foi introduzida para barrar endereço-default de produção (visando AC04), mas com isso **também rejeita `:8080` configurado explicitamente**, quebrando o comportamento do perfil legado Bling — o que viola diretamente **AC01** ("Configuração atual Bling mantém comportamento").
- **Evidência:** `0.0.0.0:8080` é aceito enquanto `:8080` explícito é recusado com mensagem de "endereço default de produção", penalizando quem já usava `:8080` no perfil legado.
- **Ação exigida pelo Checker:** remover a regra arbitrária `host=="" && port=="8080"`, preservando a proteção contra endereço implícito via `net.SplitHostPort` (validação sintática) + exigência de configuração preexistente (não gerar default silenciosamente).

## 2. Distinção R1 (bloqueante) vs. não-bloqueante

| Item | Natureza | Bloqueia AC obrigatório? |
|---|---|---|
| **R1** | Defeito de patch: regra heurística quebra AC01 | **Sim** — viola AC01 diretamente |
| Deferred 1 (validação de material público/privado ausente no perfil mkauth) | Observação | Não — o próprio Checker reconhece que é aceitável nesta fatia, pois handlers só serão ligados em 6.0b–d (AC02) |
| Deferred 2 (falha preexistente em `internal/connectorgate`) | Observação | Não — falha isolada e alheia ao escopo desta story (oráculo de teste desatualizado, não tocado pela mudança) |

**Verificação cruzada spec × dev-report × parecer:**
- Dev-report confirma que o slot `mkauth-control-plane` "ainda não abre listener nem liga handler" — corrobora que o deferred 1 é aceitável nesta rodada (AC02 delega handlers a 6.0b–d).
- Dev-report confirma que "os endereços dos dois listeners existentes são validados antes de abrir banco/listener; endereço ausente, malformado ou `:8080` é recusado" — isso **confirma textualmente** o comportamento contestado pelo Checker: a recusa de `:8080` está de fato implementada e é exatamente o que R1 identifica como regressão do perfil Bling (AC01).
- §5 (Verificação) exige que mutação no caminho real torne o teste vermelho e a restauração volte a verde — a correção de R1 deve manter essa prova contrafactual para AC01/AC04 sem reintroduzir a heurística indevida.
- §6 (Limites) confirma que a story deve implementar somente seu módulo (sem tocar `internal/connectorgate`), reforçando que o deferred 2 está corretamente fora de escopo.

Não há discrepância entre o alvo do parecer (`validateListenAddr`) e o escopo declarado no dev-report (mesma função, mesmo arquivo). O achado é preciso e rastreável.

## 3. Encaminhamento proposto

**Rework delimitado ao achado R1.** Não há base para contestação (a evidência do Checker é consistente com o próprio dev-report, que descreve a regra questionada) nem para impedimento (o defeito é local, com correção objetiva já especificada pelo Checker, sem necessidade de decisão arquitetural nova). Os itens `deferred` **não** entram no escopo desta rodada de rework — permanecem registrados para tratamento futuro (6.0b–d ou ticket de débito técnico do `connectorgate`), conforme a própria autorização do parecer.

---

## 4. Briefing para o Maker — Rework R1 (Story 6.0a, rodada 2)

**Objetivo único:** corrigir `validateListenAddr` para eliminar a regra heurística `host == "" && port == "8080"` sem reabrir nenhum outro aspecto da entrega.

**Escopo estritamente delimitado:**
- Arquivo/função alvo: `cmd/lynvia/internal/process/config.go: validateListenAddr` (único `content_path` autorizado nesta rodada).
- **Remover** a rejeição especial de `host == "" && port == "8080"`.
- **Preservar**:
  - validação sintática via `net.SplitHostPort` (endereço malformado continua recusado);
  - exigência de que o endereço venha de configuração preexistente/explícita (protege AC04 contra bind implícito em default de produção);
  - comportamento atual para `0.0.0.0:8080` (já aceito, não mexer).
- **Fora de escopo nesta rodada** (não tocar): validação de material público/privado do perfil `mkauth-control-plane` (`normalizeConfig`), e qualquer coisa em `internal/connectorgate`.

**Critérios de aceite envolvidos:**
- **AC01** — comportamento do perfil Bling deve permanecer inalterado; `:8080` configurado explicitamente deve voltar a ser aceito.
- **AC04** — nenhum servidor deve iniciar implicitamente em endereço default; a proteção deve continuar via validação sintática + exigência de configuração explícita, não por heurística de porta.

**Prova exigida (conforme §5 Verificação da spec):**
- Cenários S18/S19 mantidos; mapear entrada/ação/esperado/observado no dev-report atualizado.
- Sonda contrafactual: mutar a regra de volta (reintroduzir a heurística removida) deve tornar o teste vermelho; restaurar a correção deve voltar a verde.
- Sem `t.Skip`, sem fixtures mockadas para o caminho real de validação; testes Go sob `internal`, descobertos por `go test ./...`.

**Não fazer:**
- Não alterar lifecycle, composição de perfis, ou qualquer outro trecho de `config.go` fora de `validateListenAddr`.
- Não abrir os itens `deferred` (material público/privado do mkauth; falha em `connectorgate`) nesta rodada.
- Não tocar `protocol/` nem introduzir dependência cruzada entre módulos (§6).

**Entregável esperado:** patch mínimo em `validateListenAddr` + atualização do dev-report (seção "Escopo entregue") registrando a remoção da heurística e a prova contrafactual associada a R1, para nova rodada de checagem.
