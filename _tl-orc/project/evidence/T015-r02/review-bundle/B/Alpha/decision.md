## 1. Avaliação formal do estado da Story 6.0a

**Verdict do Checker (rodada 1): `changes_requested`**, com 1 `action_item` (R1, severidade `medium`, categoria `patch`, alvo `maker`) e 2 itens em `deferred` (severidade `low`). `rejected: []`.

Conferindo o parecer contra a spec (`§3 Critérios de aceite`) e o dev-report (`Critérios de aceite`, `Sondas contrafactuais`):

- **AC01** exige que "configuração atual Bling mantém comportamento" — cláusula de não-regressão.
- **AC04** exige que "nenhum servidor é iniciado implicitamente em endereço default de produção" e que os endereços sejam validados **por função**, não que endereços explícitos equivalentes sejam tratados de forma arbitrária.
- O dev-report confirma que a sonda M2/AC04 depende justamente de `validateListenAddr` para produzir vermelho quando a chamada é removida — ou seja, a validação existe para cumprir AC04, mas o **critério interno da heurística** (`host == "" && port == "8080"`) é o que está em disputa, não a existência da validação.

O achado R1 é consistente e bem fundamentado: a evidência citada (`0.0.0.0:8080` aceito vs `:8080` recusado) mostra que dois endereços de bind semanticamente equivalentes recebem tratamento distinto — isso não é uma leitura de "endereço implícito", é uma discriminação sintática arbitrária que pode reprovar uma configuração Bling legada que já usava `:8080` explicitamente, contrariando o AC01 sem necessidade, já que a proteção de AC04 pode ser obtida por validação sintática (`net.SplitHostPort`) mais exigência de presença de configuração prévia — sem o corte `host=="" && port=="8080"`.

## 2. R1 vs achados não-bloqueantes

| Item | Bloqueia AC obrigatório? | Enquadramento |
|---|---|---|
| **R1** — heurística de `validateListenAddr` | **Sim** — viola AC01 (regressão de comportamento Bling legado) | Defeito real, delimitado a uma função, com correção objetiva descrita no próprio `required_action` |
| Deferred 1 — validação de KeyFile ausente no perfil mkauth | Não | O próprio Checker reconhece que AC02 empurra a ligação de handlers para 6.0b–d; fora do escopo desta fatia |
| Deferred 2 — vermelho preexistente em `internal/connectorgate` | Não | Falha alheia e preexistente, já isolada pelo dev-report como fora do diff desta story |

O alvo (`cmd/lynvia/internal/process/config.go: validateListenAddr`) bate com o local citado tanto no dev-report (sonda M2) quanto no escopo declarado ("Alteração produtiva: quatro arquivos"). Não há indício de que o Checker tenha ultrapassado o escopo da story ou confundido artefato.

## 3. Encaminhamento proposto

**Rework delimitado ao achado R1.** Não há base para contestação (o achado é procedente e a evidência citada é verificável na tabela AC04 do próprio dev-report) nem para impedimento (a correção é local, sem dependência externa, sem necessidade de decisão arquitetural nova — o próprio `required_action` já aponta o caminho: manter `net.SplitHostPort` + exigência de configuração preexistente, remover o corte heurístico `host=="" && port=="8080"`).

Os dois itens `deferred` **não** entram neste rework — permanecem registrados como pendência de baixa severidade para rodadas futuras (6.0b–d ou tratamento de defeito preexistente fora desta story), conforme o próprio Checker já delimitou.

Nota de procedência: a árvore de código da rodada 1 está `not_observable` neste recorte; esta decisão e o briefing abaixo se apoiam estritamente nas citações de código e comportamento reportadas por dev-report e Checker, não em inspeção direta do diff.

## 4. Briefing — Maker, rework R1

```
story: 6-0a-configuracao-e-lifecycle-do-control-plane
rodada: rework R1 (pós changes_requested)
escopo: ESTRITAMENTE achado R1 — nenhuma outra alteração autorizada nesta rodada
target_role: maker
location: cmd/lynvia/internal/process/config.go: validateListenAddr

problema (do Checker):
  A validação heurística `host == "" && port == "8080"` altera o comportamento do
  perfil legado Bling ao recusar `:8080` explícito, enquanto `0.0.0.0:8080` (endereço
  equivalente) é aceito. Isso viola AC01 ("configuração atual Bling mantém
  comportamento"), sem necessidade, já que AC04 pode ser satisfeito sem esse corte
  arbitrário.

ação exigida:
  Remover a regra `host == "" && port == "8080"` em validateListenAddr.
  Preservar a proteção de AC04 (nenhum servidor implícito em endereço default de
  produção) por dois meios já disponíveis:
    1. validação sintática via net.SplitHostPort (endereço malformado é sempre recusado);
    2. exigência de que a configuração de endereço já exista/seja explícita antes do
       bootstrap (não permitir vazio/ausente cair em um default implícito).

fora de escopo nesta rodada (não tocar):
  - KeyFile/material público-privado do perfil mkauth-control-plane (deferred, low,
    fora da fatia atual conforme AC02/6.0b-d).
  - internal/connectorgate (vermelho preexistente e alheio ao diff desta story).
  - Qualquer outro AC (AC02, AC03) ou arquivo fora de config.go relacionado a R1.

prova exigida no re-envio:
  - Reexecutar a sonda M2/AC04 do dev-report original (remover chamadas a
    validateListenAddr → vermelho esperado; restaurar → verde) para confirmar que a
    proteção contra endereço implícito continua íntegra sem o corte heurístico.
  - Novo teste ou ajuste de teste existente que comprove que `:8080` explícito e
    `0.0.0.0:8080` explícito recebem o MESMO tratamento (ambos aceitos como
    configuração explícita válida do perfil Bling legado), fechando a regressão
    apontada em AC01.
  - Repetir a suíte de wiring do perfil Bling (os "cinco testes" citados no dev-report)
    para confirmar ausência de nova regressão.
  - content_paths: preservar exatamente os caminhos de conteúdo já declarados na
    story/spec (spec_revision "story-6.0a-r1"); esta rodada não introduz, renomeia
    nem remove content_paths — qualquer necessidade de alterá-los deve ser reportada
    como impedimento antes de qualquer escrita.

não fazer:
  - Não expandir para AC02/AC03 ou para os itens deferred.
  - Não tocar internal/connectorgate.
  - Não introduzir mock para engine/grant/endpoint/documento real (regra §5 da spec).
  - Não iniciar servidor real nem efeito externo (G5 não concedido nesta revisão).
```

Este briefing e a proposta de condução acima são o resultado final deste exercício — nenhum arquivo foi alterado e nenhum agente foi despachado, conforme o aviso restritivo da tarefa.
