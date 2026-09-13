## Avaliação formal — DW-6.0A-01 (revisão externa r1)

### O que foi encontrado (fatos verificados nas fontes congeladas)

1. **Item avaliado**: `deferred-work.md` mostra que DW-6.0A-01 já está marcado `~~RESOLVIDO em 2026-09-08~~`, com a correção (troca do literal de usage por prefixo estável em `release_test.go:242`) atribuída como "correção própria do Orquestrador", amparada no parecer em `checker-dw-6-0a-01-r1.md` — que é exatamente o arquivo em `checkpoint-C`. `release_test.diff` está com 0 bytes (consistente com diff já aplicado/commitado, não pendente).

2. **Parecer r1**: `verdict: approved`, zero `action_items`/`deferred`, três hipóteses de risco explicitamente rejeitadas com evidência (prefixo estável, robustez do teste `--version`, robustez do ciclo de vida SIGTERM). Executado por **Agy `gemini-3.8-flash-medium`**.

3. **Governança em `PROJECT.md` — pin fixado pelo usuário em 2026-09-07** ("Escolhas fixadas pelo usuário", prevalece sobre o perfil):
   - **Maker**, escopo "Tasks Native a partir de `lynvia-mkauth-connector:T004`": Agy/Antigravity `gemini-3.8-flash-high`.
   - **Checker report-only**, escopo "idem": família **Claude** (`sonnet` ou `claude-opus-5`), com a justificativa textual explícita: *"a única restrição é família independente dos Makers efetivos (Agy Gemini e Codex GPT) em sessão nova"*.
   - Ou seja: para este escopo, o catálogo permitido de Checker **exclui explicitamente Gemini e GPT**, porque são as famílias dos Makers efetivos — não é uma preferência genérica de "família diferente do autor", é uma restrição de catálogo fixa e nomeada.

4. **Classificação embutida em `checker-dw-6-0a-01-r1.md`**: rankeou como candidato primário `agy/gemini-3.8-flash-medium`, com Claude `sonnet` como "último recurso... por compartilhar a família Anthropic do autor". Essa classificação tratou o problema como independência genérica em relação à autoria (e ainda erra a autoria — `resume.json` registra `effective_authors: ["openai"]`, não Claude/Anthropic), **ignorando o pin fixo do usuário** que já nomeia Claude como único catálogo válido de Checker neste escopo, independentemente de quem assinou o diff.

5. **Resultado**: o parecer r1 foi produzido por **Agy Gemini**, candidato que o próprio `PROJECT.md` exclui nominalmente do catálogo de Checker para este escopo (por ser família de Maker). Isso não se enquadra no mecanismo de fallback `checker_independence: preferred` (que permite mesma família do autor apenas sob indisponibilidade comprovada, com registro de `same_family_fresh_session` e abertura de `review_followups`) — não há nenhum registro de indisponibilidade de Claude, nem esse fallback documentado. É simplesmente uso de candidato fora do catálogo pinado.

### Distinção exigida: candidato não autorizado vs. aprovação regular

- **Não é** uma aprovação regular meramente subótima (ex.: família independente porém não preferida, ainda dentro do catálogo geral). 
- **É** aprovação emitida por candidato explicitamente fora do catálogo fixado pelo usuário para este papel/escopo — o verdict `approved` de r1 carece de validade de governança, mesmo que o conteúdo técnico do parecer seja substantivamente razoável.
- Não há evidência de corrupção do resultado técnico (a análise do prefixo estável parece correta em si), mas a **cadeia de autoridade** que produziu esse `approved` está viciada.

### Proposta de regularização (não executada — somente proposta, modo leitura)

1. **Preservar** `checker-dw-6-0a-01-r1.md` intocado, como registro do desvio (não substituir nem apagar). Anexar (em nova revisão, fora desta sessão) uma nota de reclassificação que documenta: candidato usado (Agy Gemini) estava fora do catálogo pinado para Checker neste escopo; motivo do desvio: classificação ignorou o pin fixo e avaliou independência apenas contra autoria putativa.
2. **Nova classificação (r2)**, em sessão limpa, corrigindo os `facts`/`roles.checker.candidates` para refletir o pin: catálogo restrito a `claude/sonnet` e `claude/claude-opus-5`, efforts medium/high a critério do Classificador; excluir Gemini e GPT explicitamente como candidatos de Checker neste escopo (mesma justificativa do pin: são famílias de Maker efetivas).
3. **Nova revisão (r2)** por candidato Claude registrado, em sessão nova e sem escrita, sobre o mesmo diff de uma linha em `release_test.go:242`, cobrindo os três pontos já levantados em r1 (prefixo estável do oráculo de usage, robustez de `--version`, robustez do shutdown SIGTERM) — não como repetição vazia, mas como validação independente e autorizada dos mesmos riscos.
4. **Atualizar** `deferred-work.md`: manter o item como resolvido tecnicamente (o diff já está aplicado e passou em `make check`), mas marcar a **governança da revisão** como pendente de regularização até r2 existir — evitando reabrir o item como código, apenas a cadeia de aprovação.
5. Registrar essa ocorrência como possível padrão a monitorar: classificações que citam "independência da autoria" sem checar primeiro se há um pin de catálogo explícito no `PROJECT.md` para o escopo devem ser tratadas como suspeitas até prova em contrário.

### Briefing estruturado para a nova revisão (r2) — não despachado

```json
{
  "unit": "DW-6.0A-01",
  "revision": "r2",
  "phase": "review",
  "role": "checker",
  "catalog_restriction": {
    "allowed": [
      {"harness": "claude", "model": "sonnet"},
      {"harness": "claude", "model": "claude-opus-5"}
    ],
    "excluded": ["agy/gemini-3.8-flash-medium", "codex/gpt-5.6-terra"],
    "reason": "Pin fixado pelo usuário em 2026-09-07 (PROJECT.md, 'Escolhas fixadas pelo usuário'): Checker deste escopo deve ser família Claude, por ser família distinta dos Makers efetivos (Agy Gemini, Codex GPT)."
  },
  "prior_review_status": "r1 approved by unauthorized candidate (agy/gemini-3.8-flash-medium); preserved as deviation record, not superseded technically",
  "review_scope": {
    "file": "modules/lynvia/internal/connectorgate/release_test.go",
    "lines_of_interest": ["242 (usage prefix oracle)", "236-240 (--version output)", "245-290 (SIGTERM lifecycle)"],
    "diff_size": "1 file, 1 line"
  },
  "must_confirm": [
    "Prefixo 'uso: lynvia-mkauth-connector [--version' ainda discrimina regressão real de usage (sonda contrafactual já documentada em r1 — validar reprodutibilidade, não repetir do zero)",
    "Nenhum outro oráculo frágil equivalente no mesmo arquivo",
    "make check completo do módulo lynvia permanece verde"
  ],
  "session_requirements": "sessão nova, sem escrita, sem continuidade de contexto com r1",
  "action_on_completion": "registrar r2 na evidência da unidade; se approved, fechar a pendência de governança sem reabrir o código"
}
```

Nenhum arquivo foi modificado e nenhum agente foi despachado — esta resposta é a proposta de condução e o briefing solicitados.