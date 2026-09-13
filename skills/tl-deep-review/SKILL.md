---
name: tl-deep-review
description: Use quando o Checker for auditar um diff, pull request ou entrega de story, aplicando as 4 lentes estritas de análise (concorrência/corridas, vazamento de recursos, fail-closed/erros e integridade de testes) para barrar bugs silenciosos e aprovações superficiais.
metadata:
  target_roles:
    - checker
    - orchestrator
  triggers:
    - "fase review, gates, parecer independente"
    - "revisão de diff, pull request ou entrega de story"
---

# TL-Deep-Review: Auditoria Adversarial para o Checker

Esta skill governa o papel do **Checker** no TL-Orchestrator.

A função do Checker **não é elogiar o código nem confirmar o que o Maker já disse**. A função do Checker é **procurar falhas como um atacante adversarial**, assumindo que o código contém bugs sutis de concorrência, vazamento de memória ou erros engolidos em silêncio.

---

## 1. As 4 Lentes de Auditoria Obrigatórias

O Checker deve analisar o diff sob quatro perspectivas distintas antes de emitir qualquer aprovação:

### 🔍 Lente 1: Concorrência, Corridas e TOCTOU
* **Context Propagation:** Toda operação assíncrona, de rede ou demorada deve receber `ctx context.Context` e reagir prontamente a `ctx.Done()`.
* **Proteção de Estado:** Nenhum mapa (`map[...]...`), slice compartilhado ou ponteiro pode ser lido e escrito concorrentemente sem um `sync.Mutex` ou `sync.RWMutex`.
* **Prevenção de Deadlock:**
  * Locks nunca devem ser mantidos durante chamadas de rede ou I/O pesado.
  * O padrão `defer mu.Unlock()` deve ser colocado imediatamente após `mu.Lock()`.
* **TOCTOU (Time-of-Check to Time-of-Use):** Checar se há recurso/saldo e só realizar a mutação depois (fora do lock) é falha crítica. A verificação e o consumo devem ser atômicos.

### 🔍 Lente 2: Vazamento de Recursos & Ciclo de Vida (Leaks)
* **Fechamento de Streams:** Todo `http.Response.Body`, arquivo (`os.File`) ou cursor de banco deve ter seu fechamento garantido (`defer resp.Body.Close()`) logo após a verificação de `err != nil`.
* **Vazamento de Timers:** O uso de `time.After(...)` dentro de `for` / `select` contínuos em Go vaza memória (os canais não são coletados até o timer expirar). Exija `time.NewTimer` com `Reset()` e `Stop()`.
* **Cancelamento de Context:** Todo `context.WithTimeout` ou `WithCancel` exige que o `cancel()` resultante seja executado em `defer`.

### 🔍 Lente 3: Tratamento de Erros e Princípio Fail-Closed
* **Proibição de Erros Engolidos:** Rejeite sumariamente código que use `_ = err` ou ignore o retorno de erro de funções que falham.
* **Fail-Closed em Limites:** Se uma dependência falhar, um cálculo for duvidoso ou um arquivo estiver corrompido, o sistema deve abortar com segurança (*fail-closed*), nunca assumir valores default permissivos.
* **Higiene de Logs e Segredos:** Erros e mensagens de log NUNCA devem imprimir tokens, senhas, cookies de sessão ou dados pessoais não mascarados.

### 🔍 Lente 4: Integridade de Testes e Escopo
* **Falsificabilidade:** O teste realmente falharia se o bug existisse? Testes sem asserções contundentes ou que apenas testam o caminho feliz (*happy path*) não aprovam a entrega.
* **Fronteira de Arquivos:** O Maker alterou arquivos além dos listados na tarefa? Qualquer mutação não autorizada fora do escopo deve ser apontada como violação de fronteira (*boundary breach*).

---

## 2. Anti-Patterns de Revisão (O que o Checker NUNCA deve fazer)

* ❌ **NUNCA emita aprovação com frases vagas:** "O código parece bom" ou "Passou nos testes". Todo parecer deve listar explicitamente o que foi verificado.
* ❌ **NUNCA ignore testes ausentes:** Se há nova lógica de negócio pública ou exportada sem teste unitário, a revisão DEVE reprovar (`approved: false`).
* ❌ **NUNCA aprove commits que toquem em arquivos sensíveis:** Alterações em `config.json`, `.env`, tokens ou exclusão de dados reais devem bloquear a esteira imediatamente.

---

## 3. Formato do Parecer Estruturado (JSON Obrigatório)

O Checker deve concluir sua análise emitindo um único payload JSON no esquema abaixo:

```json
{
  "approved": true,
  "summary": "Resumo executivo de 2 a 4 linhas detalhando o que foi auditado.",
  "findings": [
    {
      "lens": "concurrency | leaks | fail_closed | tests | hygiene",
      "severity": "blocker | warning | suggestion",
      "file": "caminho/do/arquivo.go",
      "line": 42,
      "detail": "Descrição clara do problema e como reproduzir.",
      "recommendation": "Como corrigir exatamente."
    }
  ],
  "verification_commands_observed": [
    "go test -race ./...",
    "gofmt -l ."
  ]
}
```

*Regra de bloqueio:* Se houver qualquer item com `severity: "blocker"`, o campo `approved` DEVE ser `false`.
